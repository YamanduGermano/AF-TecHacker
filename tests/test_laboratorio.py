import io, json, os, sys, tempfile, threading, time, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from app.executor import Job, run
from app.resources import destination_info, executable, target_url
from app.server import create_server
from app.service import Service
from app.storage import digest
from app import reports


class LabCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('lab-tool', 'lab-second'):
            p = self.bin / name
            p.write_text('#!' + sys.executable + '\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n')
            p.chmod(0o755)
        self.env = patch.dict(os.environ, {'PATH': str(self.bin) + os.pathsep + os.environ['PATH']})
        self.env.start()
        self.svc = Service(self.root / 'dados')
        self.svc.resources.models = [{'name': 'local-test', 'digest': 'test'}]
        for name in ('lab-tool', 'lab-second'):
            self.svc.resources.add(name, 'Ferramenta de teste')
        self.svc.resources.request = lambda *a, **kw: {'message': {'content': json.dumps({'synthesis': 'Resultado registrado.', 'observations': [], 'limitations': ['Modelo simulado.'], 'proposal': None})}}
        self.s = self.svc.create_session({'title': 'Teste', 'target': 'http://127.0.0.1:3000/', 'model': 'local-test', 'authorized': True, 'plan': {k: 'Plano: ' + k for k in ('objective', 'hypotheses', 'strategy', 'tools', 'evidence')}})
        self.svc.update(self.s['id'], {'investigation': 0, 'hypothesis': 'Verificar comportamento', 'strategy': 'Comando controlado'})

    def tearDown(self):
        for job in list(self.svc.jobs.values()):
            job.cancel.set()
        self.wait_idle()
        self.env.stop()
        self.temp.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 5
        while self.svc.jobs and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.svc.jobs)

    def propose(self, args=None):
        s = self.svc.store.get(self.s['id'])
        p = self.svc.make_proposal(s, {'tool': 'lab-tool', 'args': args or ['test'], 'rationale': 'Teste', 'effects': 'Imprime argumentos'}, 0)
        s['proposals'].append(p)
        self.svc.store.save(s)
        return p

    def approve(self, p):
        return self.svc.proposal_action(self.s['id'], p['id'], 'approve', {'revision': p['revision'], 'confirmed': True})

    def test_proposal_never_executes_and_rejection_persists(self):
        p = self.propose()
        self.assertEqual(self.svc.store.get(self.s['id'])['actions'], 0)
        self.svc.proposal_action(self.s['id'], p['id'], 'reject', {'revision': 1, 'reason': 'Fora da estratégia'})
        s = Service(self.root / 'dados').store.get(self.s['id'])
        self.assertEqual(s['proposals'][0]['status'], 'rejected')
        self.assertNotIn('result', s['proposals'][0])
        self.assertEqual(s['proposals'][0]['decision']['reason'], 'Fora da estratégia')

    def test_no_shell_and_no_duplicate_approval(self):
        sentinel = self.root / 'never-created'
        args = ['; touch ' + str(sentinel), '$(touch ' + str(sentinel) + ')', 'a b', '']
        p = self.propose(args)
        self.approve(p)
        with self.assertRaises(ValueError): self.approve(p)
        self.wait_idle()
        s = self.svc.store.get(self.s['id'])
        self.assertEqual(json.loads(s['proposals'][0]['result']['stdout']), args)
        self.assertFalse(sentinel.exists())
        self.assertEqual(s['actions'], 1)
        self.assertEqual(len(s['investigations'][0]['syntheses']), 1)

    def test_edit_requires_new_revision_preserves_original(self):
        p = self.propose(['before'])
        s = self.svc.proposal_action(self.s['id'], p['id'], 'edit', {'revision': 1, 'tool': 'lab-second', 'args': ['after'], 'reason': 'Adequação'})
        self.assertEqual(s['proposals'][0]['revision'], 2)
        self.assertEqual(s['proposals'][0]['original']['args'], ['before'])
        self.assertEqual(s['actions'], 0)
        with self.assertRaises(ValueError): self.approve(p)
        self.approve(s['proposals'][0])
        self.wait_idle()
        self.assertEqual(json.loads(self.svc.store.get(self.s['id'])['proposals'][0]['result']['stdout']), ['after'])

    def test_changed_binary_suspends(self):
        p = self.propose()
        with (self.bin / 'lab-tool').open('a') as f: f.write('# altered\n')
        with self.assertRaisesRegex(ValueError, 'mudou'): self.approve(p)
        self.assertEqual(self.svc.store.get(self.s['id'])['proposals'][0]['status'], 'suspended')

    def test_removed_tool_refused(self):
        p = self.propose()
        self.svc.resources.catalog = []
        with self.assertRaisesRegex(ValueError, 'catálogo'): self.approve(p)

    def test_action_limit(self):
        p = self.propose()
        s = self.svc.store.get(self.s['id'])
        s['actions'] = s['limits']['max_actions']
        self.svc.store.save(s)
        with self.assertRaisesRegex(ValueError, 'Limite'): self.approve(p)

    def test_confirmation_required(self):
        p = self.propose()
        with self.assertRaisesRegex(ValueError, 'Confirme'):
            self.svc.proposal_action(self.s['id'], p['id'], 'approve', {'revision': 1})

    def test_adaptive_model_loop_no_auto_execution(self):
        responses = [
            {'synthesis': 'Hipótese não verificada', 'proposal': {'tool': 'lab-tool', 'args': ['one'], 'rationale': 'Primeiro passo', 'effects': 'Saída local'}},
            {'synthesis': 'Saída recebida', 'proposal': {'tool': 'lab-second', 'args': ['two'], 'rationale': 'Passo adaptado', 'effects': 'Saída local'}}]
        self.svc.resources.request = lambda *a, **kw: {'message': {'content': json.dumps(responses.pop(0))}}
        self.svc.ask(self.s['id'], {'investigation': 0, 'message': 'Comece'})
        self.wait_idle()
        s = self.svc.store.get(self.s['id'])
        self.assertEqual(s['actions'], 0)
        self.approve(s['proposals'][0])
        self.wait_idle()
        s = self.svc.store.get(self.s['id'])
        self.assertEqual(s['actions'], 1)
        self.assertEqual(s['proposals'][1]['tool'], 'lab-second')
        self.assertEqual(s['proposals'][1]['status'], 'pending')
        contexts = [a for a in s['artifacts'] if a['origin'].startswith('contexto')]
        self.assertEqual(len(contexts), 2)
        self.assertIn('one', (self.svc.store.directory(s['id']) / 'arquivos' / contexts[-1]['name']).read_text())

    def test_invalid_model_response_preserved_without_proposal(self):
        self.svc.resources.request = lambda *a, **kw: {'message': {'content': 'not json'}}
        self.svc.ask(self.s['id'], {'investigation': 0})
        self.wait_idle()
        s = self.svc.store.get(self.s['id'])
        self.assertEqual(s['proposals'], [])
        self.assertEqual(s['chat'][-1]['content'], 'not json')
        self.assertTrue(any(e['kind'] == 'error' for e in s['events']))

    def test_stop_discards_late_model_proposal(self):
        entered, release = threading.Event(), threading.Event()
        def response(*a, **kw):
            entered.set(); release.wait(2)
            return {'message': {'content': json.dumps({'synthesis': 'Late', 'proposal': {'tool': 'lab-tool', 'args': [], 'rationale': 'x', 'effects': 'x'}})}}
        self.svc.resources.request = response
        self.svc.ask(self.s['id'], {'investigation': 0})
        self.assertTrue(entered.wait(1))
        self.svc.stop(self.s['id']); release.set(); self.wait_idle()
        s = self.svc.store.get(self.s['id'])
        self.assertEqual(s['status'], 'paused')
        self.assertEqual(s['proposals'], [])
        self.assertTrue(s['chat'][-1]['discarded'])

    def test_refresh_never_executes_registered_tools_or_changes_session_model(self):
        self.svc.resources.request = lambda *a, **kw: {'models': [{'name': 'new-model'}]}
        with patch('app.resources.run') as mock:
            snapshot = self.svc.resources.refresh()
            mock.assert_not_called()
        self.assertEqual(snapshot['models'][0]['name'], 'new-model')
        self.assertEqual(self.svc.store.get(self.s['id'])['model'], 'local-test')

    def test_help_requires_one_time_approval(self):
        request = self.svc.prepare_help('lab-tool')
        self.assertEqual(request['status'], 'pending')
        with self.assertRaises(ValueError): self.svc.approve_help(request['id'], {})
        self.svc.approve_help(request['id'], {'confirmed': True})
        with self.assertRaises(ValueError): self.svc.approve_help(request['id'], {'confirmed': True})
        self.assertIn('--help', self.svc.resources.get('lab-tool')['documentation']['content'])

    def test_three_investigations_restoration_revision_export_hashes(self):
        for i in range(3): self.svc.update(self.s['id'], {'investigation': i, 'hypothesis': f'H{i}', 'strategy': f'S{i}', 'conclusion': f'C{i}'})
        self.svc.restore(self.s['id'], {'investigation': 1, 'mode': 'LAN', 'procedure': 'Reinício manual', 'confirmation': 'Estado conferido', 'confirmed': True})
        s = self.svc.store.get(self.s['id'])
        s['revisions'].append({'id': 'revision', 'field': 'strategy', 'value': 'Sugestão', 'status': 'pending'})
        self.svc.store.save(s)
        self.svc.revision(s['id'], 'revision', {'status': 'modified', 'value': 'Texto final', 'reason': 'Decisão humana'})
        s = self.svc.store.get(s['id'])
        self.assertNotEqual(s['initial_plan']['strategy'], s['plan']['strategy'])
        self.assertEqual(s['restorations'][0]['investigation'], 1)
        self.assertEqual(len(s['investigations']), 3)
        draft = reports.report(s)
        self.assertIn('PENDENTE', draft)
        self.assertIn('C2', draft)
        a = self.svc.store.artifact(s, 'evidence.txt', b'test evidence', 'fixture')
        self.svc.store.save(s)
        data, _, _ = reports.export(self.svc.store, s, 'files')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for item in json.loads(z.read('manifesto.json')):
                self.assertEqual(digest(z.read(item['name'])), item['sha256'])
        (self.svc.store.directory(s['id']) / 'arquivos' / a['name']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Hash'): reports.export(self.svc.store, s, 'files')

    def test_restart_never_resumes_command(self):
        self.propose()
        s = self.svc.store.get(self.s['id']); s['status'] = 'running'; s['proposals'][0]['status'] = 'running'
        self.svc.store.save(s)
        service = Service(self.root / 'dados')
        restored = service.store.get(s['id'])
        self.assertEqual(restored['status'], 'paused')
        self.assertEqual(restored['proposals'][0]['status'], 'interrupted')
        self.assertEqual(service.jobs, {})

    def test_http_host_origin_token_download_and_update(self):
        server = create_server(self.svc, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with urlopen(base + '/api/bootstrap') as r: bootstrap = json.load(r)
            with urlopen(base + '/') as r:
                self.assertIn('Laboratório', r.read().decode())
                self.assertIn("frame-ancestors 'none'", r.headers['Content-Security-Policy'])
            for headers in ({}, {'X-Lab-Token': bootstrap['token'], 'Origin': 'http://evil.example'}, {'X-Lab-Token': bootstrap['token'], 'Host': 'evil.example'}):
                req = Request(base + '/api/resources/refresh', data=b'{}', headers={'Content-Type': 'application/json', **headers})
                with self.assertRaises(HTTPError) as raised: urlopen(req)
                self.assertEqual(raised.exception.code, 403)
            with urlopen(base + '/api/sessions/' + self.s['id'] + '/export/files') as r:
                self.assertEqual(r.headers['Content-Type'], 'application/zip')
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(r.read())))
            req = Request(base + '/api/sessions/' + self.s['id'] + '/update', data=json.dumps({'investigation': 2, 'hypothesis': 'HTTP test'}).encode(), headers={'Content-Type': 'application/json', 'X-Lab-Token': bootstrap['token'], 'Origin': base})
            with urlopen(req) as r: self.assertEqual(json.load(r)['investigations'][2]['hypothesis'], 'HTTP test')
        finally:
            server.shutdown(); server.server_close(); thread.join(2)


class ExecutorTests(unittest.TestCase):
    def test_timeout_and_output_limit(self):
        r = run([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=.12)
        self.assertEqual(r['reason'], 'timeout'); self.assertLess(r['duration'], 2)
        r = run([sys.executable, '-c', 'print("x"*50000)'], output_limit=1000)
        self.assertEqual(r['reason'], 'output_limit'); self.assertLessEqual(len(r['stdout'])+len(r['stderr']),1000)

    def test_closed_pipes_still_timeout(self):
        r = run([sys.executable, '-c', 'import os,time;os.close(1);os.close(2);time.sleep(4)'], timeout=.15)
        self.assertEqual(r['reason'], 'timeout'); self.assertLess(r['duration'], 2)

    def test_cancel_and_failed_command(self):
        job = Job(); timer = threading.Timer(.1, job.cancel.set); timer.start()
        r = run([sys.executable, '-c', 'import time;time.sleep(10)'], job=job); timer.join()
        self.assertEqual(r['reason'], 'interrupted')
        r = run([sys.executable, '-c', 'import sys;print("failed",file=sys.stderr);sys.exit(7)'])
        self.assertEqual(r['exit_code'], 7); self.assertIn('failed', r['stderr'])

    def test_destination_warning_and_input_validation(self):
        target_url('http://192.168.1.50:3000/')
        with self.assertRaises(ValueError): target_url('file:///etc/passwd')
        with self.assertRaises(ValueError): executable('/bin/sh')
        d = destination_info(['http://192.168.1.60:4000/', '-p', '80'], 'http://192.168.1.50:3000/')
        self.assertGreaterEqual(len(d['warnings']), 2)
        self.assertEqual(destination_info(['http://192.168.1.50:3000/'], 'http://192.168.1.50:3000/')['warnings'], [])


if __name__ == '__main__': unittest.main()
