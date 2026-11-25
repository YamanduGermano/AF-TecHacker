"""Global Markdown catalog; sessions select which installed guides to activate."""
import copy
import json
import os
import re
from pathlib import Path

from .resources import text
from .storage import digest, now, uid

MAX_ACTIVE = 3
MAX_INSTRUCTIONS = 4800
DEFAULTS = Path(__file__).parent / 'default_skills'


class Skills:
    def __init__(self, store, directory=None):
        self.store = store
        self.root = Path(directory or store.root.parent / 'skills').resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'skills.json'
        self.records = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []
        changed = not self.path.exists()
        for record in json.loads((DEFAULTS / 'skills.json').read_text(encoding='utf-8')):
            if any(s['id'] == record['id'] for s in self.records):
                continue
            path = self.file_path(record)
            if not path.exists():
                self.write_markdown(path, (DEFAULTS / record['file']).read_text(encoding='utf-8'))
            self.records.append(record)
            changed = True
        legacy = store.root / 'skills.json'
        if legacy.exists():
            for record in json.loads(legacy.read_text(encoding='utf-8')):
                if not any(s['id'] == record['id'] for s in self.records):
                    self.import_legacy(record)
                    changed = True
        if changed:
            self.store.write(self.path, self.records)

    def file_path(self, record):
        filename = record.get('file', '')
        if not isinstance(filename, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*\.md', filename):
            raise ValueError('Caminho de Markdown inválido no catálogo de skills.')
        path = self.root / filename
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError('O Markdown da skill deve ser um arquivo dentro da pasta de skills.')
        return path

    def instructions(self, value):
        if not text(value, 2400, field='Instruções da skill'):
            raise ValueError('Informe as instruções da skill.')
        if len(value) > 2400:
            raise ValueError('Instruções da skill: limite de 2400 caracteres.')
        return value

    def write_markdown(self, path, content):
        temp = path.with_name(path.name + '.' + uid() + '.tmp')
        try:
            with temp.open('w', encoding='utf-8', newline='') as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def import_legacy(self, old):
        skill_id = old['id']
        if not isinstance(skill_id, str) or not re.fullmatch(r'[a-z0-9-]{1,80}', skill_id):
            raise ValueError('ID inválido no catálogo antigo de skills.')
        content = self.instructions(old['instructions'])
        record = {k: old[k] for k in ('id', 'name', 'description', 'created_at', 'original_filename') if k in old}
        record.update(file=skill_id + '.md', source=old.get('source', 'importada'))
        path = self.file_path(record)
        if not path.exists():
            self.write_markdown(path, content)
        self.records.append(record)

    def migrate_session(self, session):
        changed = False
        for old in session.get('skills', []):
            if not any(s['id'] == old['id'] for s in self.records):
                self.import_legacy(old)
                self.store.write(self.path, self.records)
            record = next(s for s in self.records if s['id'] == old['id'])
            if old.get('file') != record['file']:
                old['file'] = record['file']
                changed = True
        return changed

    def catalog(self):
        result = []
        for record in self.records:
            item = copy.deepcopy(record)
            try:
                path = self.file_path(record)
                if path.stat().st_size > 12000:
                    raise ValueError('Arquivo de instruções excede o limite de tamanho.')
                content = self.instructions(path.read_bytes().decode('utf-8'))
                item.update(instructions=content, sha256=digest(content.encode()), available=True)
            except (OSError, UnicodeError, ValueError) as exc:
                item.update(instructions='', sha256=None, available=False, error='Skill indisponível: ' + str(exc))
            result.append(item)
        return result

    def add(self, data):
        name = text(data.get('name', ''), 80, field='Nome da skill')
        description = text(data.get('description', ''), 180, field='Descrição da skill')
        content = self.instructions(data.get('instructions', ''))
        if not name:
            raise ValueError('Informe o nome da skill.')
        if len(self.records) >= 20:
            raise ValueError('Limite de 20 skills no catálogo atingido.')
        original = text(data.get('filename', ''), 200, field='Nome do Markdown').replace('\\', '/').split('/')[-1]
        stem = re.sub(r'[^a-zA-Z0-9_-]+', '-', Path(original or name).stem).strip('-')[:60] or 'instrucoes'
        skill_id = 'custom-' + uid()
        record = {'id': skill_id, 'name': name, 'description': description, 'created_at': now(),
                  'file': skill_id + '-' + stem + '.md', 'original_filename': original or None, 'source': 'importada'}
        path = self.file_path(record)
        self.write_markdown(path, content)
        self.records.append(record)
        try:
            self.store.write(self.path, self.records)
        except Exception:
            self.records.pop()
            path.unlink(missing_ok=True)
            raise
        return {**record, 'instructions': content, 'sha256': digest(content.encode()), 'available': True}

    def activate(self, session, skill_id, origin, index=None):
        skill = next((s for s in self.catalog() if s['id'] == skill_id), None)
        if not skill:
            raise ValueError('Skill não encontrada no catálogo global: ' + str(skill_id)[:80])
        if not skill['available']:
            raise ValueError(skill['error'])
        active = session.setdefault('skills', [])
        if any(s['id'] == skill_id for s in active):
            return False
        if origin == 'model' and skill_id in session.get('disabled_skills', []):
            raise ValueError('Skill desativada pelo usuário nesta sessão: ' + skill['name'])
        self.check_capacity(session, skill['instructions'])
        record = {**skill, 'installed_at': now(), 'installed_by': origin}
        artifact = self.store.artifact(session, skill_id + '.md', skill['instructions'].encode(), 'skill: ' + skill['name'])
        record['artifact_id'] = artifact['id']
        active.append(record)
        session['disabled_skills'] = [sid for sid in session.get('disabled_skills', []) if sid != skill_id]
        self.store.event(session, 'skill_activated', 'Skill ativada nesta sessão ' + ('pelo modelo: ' if origin == 'model' else 'pelo usuário: ') + skill['name'],
                         skill_id=skill_id, artifact_id=artifact['id'], investigation=index, origin=origin)
        return True

    def refresh_active(self, session):
        """Reload global files before inference; session copies are audit snapshots."""
        catalog = {s['id']: s for s in self.catalog()}
        resolved = []
        for active in session.get('skills', []):
            skill = catalog.get(active['id'])
            if not skill or not skill['available']:
                raise ValueError('Skill ativa indisponível: ' + active['name'] + '. Corrija o Markdown ou desative a skill.')
            resolved.append((active, skill))
        if sum(len(s['instructions']) for _, s in resolved) > MAX_INSTRUCTIONS:
            raise ValueError('As skills ativas excedem 4800 caracteres após a edição dos arquivos. Desative uma skill ou reduza as instruções.')
        for active, skill in resolved:
            if active.get('sha256') != skill['sha256']:
                artifact = self.store.artifact(session, skill['file'], skill['instructions'].encode(), 'skill atualizada: ' + skill['name'])
                active['artifact_id'] = artifact['id']
                self.store.event(session, 'skill_updated', 'Markdown atualizado no contexto: ' + skill['name'], skill_id=skill['id'], artifact_id=artifact['id'])
            active.update(skill)

    def check_capacity(self, session, instructions):
        active = session.get('skills', [])
        if len(active) >= MAX_ACTIVE or sum(len(s['instructions']) for s in active) + len(instructions) > MAX_INSTRUCTIONS:
            raise ValueError('Limite de skills ativas: 3 skills e 4800 caracteres de instruções. Desative uma antes de ativar outra.')

    def remove(self, session, skill_id):
        skill = next((s for s in session.get('skills', []) if s['id'] == skill_id), None)
        if not skill:
            raise ValueError('Skill não está ativa nesta sessão.')
        session['skills'] = [s for s in session['skills'] if s['id'] != skill_id]
        session['disabled_skills'] = list(dict.fromkeys([*session.get('disabled_skills', []), skill_id]))
        self.store.event(session, 'skill_removed', 'Skill desativada pelo usuário: ' + skill['name'], skill_id=skill_id)

    def available(self, session):
        active = {s['id'] for s in session.get('skills', [])}
        if len(active) >= MAX_ACTIVE:
            return []
        remaining = MAX_INSTRUCTIONS - sum(len(s['instructions']) for s in session.get('skills', []))
        disabled = set(session.get('disabled_skills', []))
        return [{k: s[k] for k in ('id', 'name', 'description')} for s in self.catalog()
                if s['available'] and s['id'] not in active | disabled and len(s['instructions']) <= remaining]
