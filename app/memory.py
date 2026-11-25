"""Bounded investigation memory. Full logs stay on disk, outside the prompt."""
import copy
import hashlib
import json
from .storage import now

CONTEXT_LIMIT = 14000


def clip(value, limit):
    value = value if isinstance(value, str) else ''
    if len(value) <= limit:
        return value
    half = max(0, (limit - 36) // 2)
    return value[:half] + '\n[… trecho omitido …]\n' + value[-half:]


def attempts(session, index):
    return [p for p in session['proposals'] if p['investigation'] == index]


def evidence_index(session, index):
    owners = {}
    for p in attempts(session, index):
        for aid in p.get('result', {}).get('artifacts', []):
            owners[aid] = p
    return {a['id']: {**a, 'proposal_id': owners[a['id']]['id'], 'command': owners[a['id']]['command']}
            for a in session['artifacts'] if a['id'] in owners}


def latest_result(session, index):
    return next((p for p in reversed(attempts(session, index)) if p.get('result')), None)


def get_memory(session, index):
    inv = session['investigations'][index]
    if isinstance(inv.get('memory'), dict):
        return copy.deepcopy(inv['memory'])
    # Old sessions bootstrap from the latest synthesis, without inventing citations.
    last = inv['syntheses'][-1] if inv['syntheses'] else {}
    findings, seen = [], set()
    for synthesis in reversed(inv['syntheses']):
        for observation in synthesis.get('observations', []):
            if not isinstance(observation, str) or observation.strip().casefold() in seen:
                continue
            seen.add(observation.strip().casefold())
            findings.append({'conclusion': clip(observation, 350), 'evidence_ids': []})
            if len(findings) == 6:
                break
        if len(findings) == 6:
            break
    return {'version': 0, 'summary': clip(last.get('synthesis', ''), 1500),
            'findings': findings,
            'open_questions': [clip(last['next_question'], 350)] if last.get('next_question') else [],
            'next_steps': [], 'last_result_id': None,
            'source': 'latest_legacy_synthesis' if last else 'empty'}


def update_memory(session, index, parsed, synthesis_id):
    inv = session['investigations'][index]
    previous = get_memory(session, index)
    raw = parsed.get('memory')
    valid = evidence_index(session, index)
    warnings = []
    if not isinstance(raw, dict):
        # Keep old findings when a model omits memory; do not erase prior conclusions.
        raw = {**previous, 'summary': parsed.get('synthesis', previous['summary'])}
    findings = []
    for item in raw.get('findings', [])[:8] if isinstance(raw.get('findings'), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('conclusion'), str):
            continue
        refs = item.get('evidence_ids', [])
        refs = refs[:4] if isinstance(refs, list) else []
        kept = []
        for ref in refs:
            if isinstance(ref, str) and ref in valid:
                kept.append(ref)
            else:
                warnings.append('Referência inexistente ou de outra investigação removida da memória: ' + str(ref)[:80])
        findings.append({'conclusion': clip(item['conclusion'], 450), 'evidence_ids': list(dict.fromkeys(kept))})
    def texts(key):
        values = raw.get(key, [])
        return [clip(v, 350) for v in values[:5] if isinstance(v, str)] if isinstance(values, list) else []
    last = latest_result(session, index)
    memory = {'version': previous.get('version', 0) + 1, 'updated_at': now(),
              'summary': clip(raw.get('summary') or parsed.get('synthesis', ''), 1500),
              'findings': findings, 'open_questions': texts('open_questions'), 'next_steps': texts('next_steps'),
              'last_result_id': last['id'] if last else None, 'source_synthesis_id': synthesis_id,
              'source': 'model_consolidation' if isinstance(parsed.get('memory'), dict) else 'summary_fallback'}
    if previous.get('version') or previous.get('summary'):
        inv.setdefault('memory_history', []).append(previous)
    inv['memory'] = memory
    return warnings


def fingerprint(proposal):
    raw = json.dumps([proposal['tool'], proposal['args']], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def repetitions(session, proposal):
    key = fingerprint(proposal)
    return [p for p in attempts(session, proposal['investigation'])
            if p.get('status') not in ('pending', 'running') and fingerprint(p) == key]


def read_evidence(store, session, index, ids):
    """Only recorded execution files from this investigation; never arbitrary paths."""
    available = evidence_index(session, index)
    result = []
    seen = set()
    for aid in ids[:2]:
        if not isinstance(aid, str) or aid not in available:
            result.append({'id': str(aid)[:80], 'error': 'Evidência não registrada nesta investigação.'})
            continue
        if aid in seen:
            continue
        seen.add(aid)
        a = available[aid]
        root = store.directory(session['id']) / 'arquivos'
        path = root / a['name']
        if path.is_symlink() or path.parent != root or path.name != a['name'] or not path.is_file():
            result.append({'id': aid, 'error': 'Arquivo ausente ou caminho inválido.'})
            continue
        hasher = hashlib.sha256()
        head, tail, size = bytearray(), b'', 0
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
                size += len(chunk)
                if len(head) < 1800:
                    head.extend(chunk[:1800-len(head)])
                tail = (tail + chunk)[-1800:]
        if hasher.hexdigest() != a['sha256']:
            result.append({'id': aid, 'error': 'Hash divergente; evidência não fornecida ao modelo.'})
            continue
        if b'\x00' in head or a['name'].endswith('.zip'):
            content = '[Arquivo binário; abra-o na interface para inspeção.]'
        elif size <= len(head):
            content = bytes(head).decode('utf-8', errors='replace')
        elif size <= 3600:
            # Avoid duplicated bytes in overlapping head/tail windows.
            content = (bytes(head) + tail[-(size-len(head)):]).decode('utf-8', errors='replace')
        else:
            content = bytes(head).decode('utf-8', errors='replace') + '\n[… arquivo abreviado …]\n' + tail.decode('utf-8', errors='replace')
        result.append({'id': aid, 'name': a['name'], 'sha256': a['sha256'], 'command': clip(a['command'], 500),
                       'content': clip(content, 2400), 'truncated': size > 2400, 'bytes': size})
    return result


def build_context(session, resources, index, retrieved=None, feedback=''):
    inv = session['investigations'][index]
    mem = get_memory(session, index)
    entries = attempts(session, index)
    last = latest_result(session, index)
    files = evidence_index(session, index)
    human = next((m for m in reversed(session['chat']) if m.get('investigation') == index and m['role'] == 'user'
                  and m.get('origin') not in ('execution', 'command_edit') and m.get('visibility') != 'internal'), None)
    ledger = []
    for p in entries[-12:]:
        r = p.get('result', {})
        ledger.append({'id': p['id'], 'command': clip(p['command'], 450), 'status': p['status'],
                       'origin': p.get('origin', 'model'),
                       'exit_code': r.get('exit_code'), 'reason': r.get('reason'),
                       'evidence_ids': r.get('artifacts', [])[:3],
                       'decision': clip(p.get('decision', {}).get('reason', ''), 180),
                       'human_interventions': [{'before': clip(e['command'], 250), 'reason': clip(e['reason'], 180)} for e in p.get('edits', [])[-1:]]})
    wanted = []
    for finding in mem.get('findings', []):
        wanted.extend(finding.get('evidence_ids', []))
    if last:
        wanted.extend(last['result'].get('artifacts', []))
    wanted.extend(list(files)[-8:])
    wanted = list(dict.fromkeys(wanted))[-16:]
    file_refs = [{k: clip(files[aid][k], 300) if k in ('name', 'command') else files[aid][k]
                  for k in ('id', 'name', 'sha256', 'command')} for aid in wanted if aid in files]
    tools = []
    available = [t for t in resources['tools'] if t['resolved']]
    doc_budget = 2400
    for t in available[:20]:
        doc = t.get('documentation') or {}
        excerpt = clip(doc.get('content', ''), min(600, doc_budget)) if doc_budget >= 80 else ''
        doc_budget -= len(excerpt)
        tools.append({'name': t['name'], 'description': clip(t['description'], 180),
                      'documentation': {'source': doc.get('source'), 'sha256': doc.get('sha256'), 'excerpt': excerpt}})
    recent = None
    if last:
        r = last['result']
        recent = {'proposal_id': last['id'], 'command': clip(last['command'], 1400),
                  'origin': last.get('origin', 'model'), 'objective': clip(last.get('rationale', ''), 400),
                  'new_since_memory': mem.get('last_result_id') != last['id'], 'status': last['status'],
                  'exit_code': r['exit_code'], 'reason': r['reason'], 'at': r.get('at'),
                  'stdout_excerpt': clip(r.get('stdout', ''), 2200), 'stderr_excerpt': clip(r.get('stderr', ''), 1000),
                  'evidence_ids': r.get('artifacts', [])[:6], 'excerpt_only': True}
    context = {'target': session['target'],
               'plan': {k: clip(v, 400) for k, v in session['plan'].items()},
               'investigation': {k: clip(inv.get(k, ''), 500) for k in ('title', 'hypothesis', 'strategy', 'conclusion', 'evidence')},
               'memory': mem, 'attempts': ledger, 'attempt_count': len(entries),
               'active_skills': [{k: s[k] for k in ('id', 'name', 'instructions', 'sha256')} for s in session.get('skills', [])],
               'available_skills': copy.deepcopy(resources.get('available_skills', [])),
               'evidence_index': file_refs, 'retrieved_evidence': copy.deepcopy(retrieved or []), 'tools': tools,
               'last_restoration': [{k: clip(v, 350) if isinstance(v, str) else v for k, v in session['restorations'][-1].items()}] if session['restorations'] else [],
               'validation_feedback': clip(feedback, 1200), 'latest_result': recent,
               'latest_user_request': clip(human['content'], 3500) if human else 'Prossiga a partir das evidências registradas.'}
    # Newest evidence and latest user instruction are retained; drop background first.
    def size(): return len(json.dumps(context, ensure_ascii=False))
    if size() > CONTEXT_LIMIT:
        context['available_skills'] = [{'id': s['id']} for s in context['available_skills']]
        for t in context['tools']:
            t['documentation']['excerpt'] = ''
        context['context_note'] = 'Documentação abreviada para priorizar memória e resultado recente.'
    if size() > CONTEXT_LIMIT:
        context['attempts'] = ledger[-6:]
        context['evidence_index'] = file_refs[-8:]
        context['memory']['findings'] = mem.get('findings', [])[:6]
    if size() > CONTEXT_LIMIT:
        context['memory']['summary'] = clip(mem.get('summary', ''), 800)
        for item in context['retrieved_evidence']:
            if 'content' in item: item['content'] = clip(item['content'], 1000)
        for finding in context['memory'].get('findings', []):
            finding['conclusion'] = clip(finding['conclusion'], 250)
    if size() > CONTEXT_LIMIT:
        context['attempts'] = ledger[-3:]
        context['evidence_index'] = file_refs[-4:]
        context['tools'] = [{'name': t['name'], 'description': clip(t['description'], 80)} for t in tools]
        context['memory']['open_questions'] = mem.get('open_questions', [])[:2]
        context['memory']['next_steps'] = mem.get('next_steps', [])[:2]
    if size() > CONTEXT_LIMIT:
        context['plan'] = {k: clip(session['plan'].get(k, ''), 300) for k in ('objective', 'strategy')}
        context['investigation'] = {k: clip(inv.get(k, ''), 300) for k in ('title', 'hypothesis', 'conclusion')}
        context['tools'] = [{'name': t['name']} for t in tools]
        context['memory']['summary'] = clip(mem.get('summary', ''), 600)
        context['memory']['findings'] = context['memory'].get('findings', [])[:4]
        context['attempts'] = [{'id': p['id'], 'command': clip(p['command'], 200), 'status': p['status']} for p in ledger[-3:]]
        context['evidence_index'] = [{'id': f['id'], 'name': clip(f['name'], 100), 'sha256': f['sha256']} for f in file_refs[-4:]]
        for item in context['retrieved_evidence']:
            if 'content' in item: item['content'] = clip(item['content'], 600)
            if 'command' in item: item['command'] = clip(item['command'], 200)
        if recent:
            recent['command'] = clip(recent['command'], 600)
            recent['stdout_excerpt'] = clip(recent['stdout_excerpt'], 1500)
            recent['stderr_excerpt'] = clip(recent['stderr_excerpt'], 500)
        context['context_note'] = 'Histórico, documentação e notas abreviados; memória, último resultado e pedido atual têm prioridade.'
    if size() > CONTEXT_LIMIT:
        context['latest_user_request'] = clip(context['latest_user_request'], 2200)
    if size() > CONTEXT_LIMIT:
        # Installed instructions are kept intact; compact discovery/background first.
        context['available_skills'] = []
        context['active_skills'] = [{'id': s['id'], 'instructions': s['instructions']} for s in context['active_skills']]
        context['plan'] = {'objective': clip(session['plan'].get('objective', ''), 250)}
        context['investigation'] = {k: clip(inv.get(k, ''), 180) for k in ('title', 'hypothesis')}
        context['memory']['summary'] = clip(mem.get('summary', ''), 400)
        context['memory']['findings'] = [{'conclusion': clip(f.get('conclusion', ''), 180),
                                         'evidence_ids': f.get('evidence_ids', [])[:2]}
                                        for f in mem.get('findings', [])[:2]]
        context['memory']['open_questions'] = []
        context['memory']['next_steps'] = []
        context['attempts'] = context['attempts'][-2:]
        context['evidence_index'] = [{'id': f['id'], 'name': clip(f['name'], 80)} for f in file_refs[-4:]]
        context['retrieved_evidence'] = [{k: clip(v, 350 if k == 'content' else 100) if isinstance(v, str) else v
                                        for k, v in item.items() if k in ('id', 'name', 'sha256', 'content', 'error')}
                                       for item in context['retrieved_evidence']]
        context['last_restoration'] = [{k: clip(v, 120) if isinstance(v, str) else v for k, v in r.items()}
                                       for r in context['last_restoration']]
        if recent:
            recent['command'] = clip(recent['command'], 400)
            recent['objective'] = clip(recent['objective'], 180)
            recent['stdout_excerpt'] = clip(recent['stdout_excerpt'], 1000)
            recent['stderr_excerpt'] = clip(recent['stderr_excerpt'], 300)
        context['context_note'] = 'Contexto abreviado: skills ativas preservadas; catálogo omitido. Pedido atual, memória e último resultado mantidos com trechos limitados.'
    if size() > CONTEXT_LIMIT:
        raise ValueError('Contexto compacto excedeu o limite. Reduza o tamanho do pedido atual ou das anotações do grupo.')
    return context
