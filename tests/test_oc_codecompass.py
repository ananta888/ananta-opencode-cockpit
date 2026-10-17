#!/usr/bin/env python3
"""Tests fuer oc-codecompass gegen einen Mock-Hub (keine echten API-Calls)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OC_CC = Path(__file__).resolve().parent.parent / 'oc-codecompass' / 'oc-codecompass'


class MockHub(BaseHTTPRequestHandler):
    """Minimaler Ananta-Hub: /login, /refresh-token, /v1/mcp, /v1/mcp/capabilities."""

    state = {'refresh_calls': 0, 'tool_calls': []}

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        if self.path == '/v1/mcp/capabilities':
            if auth != 'Bearer goodtoken':
                return self._json(401, {'message': 'unauthorized'})
            return self._json(200, {'object': 'ananta.mcp.capabilities',
                                    'counts': {'tools': 16, 'resources': 6},
                                    'policy': {'enabled': True}})
        self._json(404, {'message': 'not found'})

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        try:
            body = json.loads(self.rfile.read(size) or b'{}')
        except ValueError:
            body = {}
        if self.path == '/login':
            if body.get('username') == 'u' and body.get('password') == 'p':
                return self._json(200, {'data': {'access_token': 'goodtoken',
                                                 'refresh_token': 'r1'}})
            return self._json(401, {'message': 'unauthorized'})
        if self.path == '/refresh-token':
            MockHub.state['refresh_calls'] += 1
            if body.get('token') in ('r1', 'r2'):
                return self._json(200, {'data': {'access_token': 'goodtoken',
                                                 'refresh_token': 'r2'}})
            return self._json(401, {'message': 'unauthorized'})
        if self.path == '/v1/mcp':
            if self.headers.get('Authorization') != 'Bearer goodtoken':
                return self._json(401, {'message': 'unauthorized'})
            method = body.get('method')
            if method == 'ping':
                return self._json(MockHub.state.get('ping_status', 200),
                                  {'jsonrpc': '2.0', 'id': body.get('id'), 'result': {}})
            if method == 'tools/list':
                return self._json(200, {'jsonrpc': '2.0', 'id': body.get('id'),
                                        'result': {'tools': [
                                            {'name': 'codecompass.search', 'description': 'd'},
                                            {'name': 'codecompass.retrieve', 'description': 'e'}]}})
            if method == 'tools/call':
                MockHub.state['tool_calls'].append(body.get('params', {}).get('name'))
                return self._json(200, {'jsonrpc': '2.0', 'id': body.get('id'),
                                        'result': {'content': [{'type': 'text', 'text': '{}'}]}})
            return self._json(200, {'jsonrpc': '2.0', 'id': body.get('id'),
                                    'error': {'code': -32601, 'message': 'method_not_found'}})
        self._json(404, {'message': 'not found'})


class OcCodecompass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), MockHub)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.tmp = Path(tempfile.mkdtemp(prefix='ac-occ-'))
        (cls.tmp / '.config/ananta-cockpit').mkdir(parents=True, exist_ok=True)
        (cls.tmp / '.config/ananta-cockpit/codecompass.json').write_text(
            json.dumps({'hub_url': f'http://127.0.0.1:{cls.port}',
                        'server_name': 'ananta_codecompass'}))
        cls.state = cls.tmp / '.state'
        cls.env = dict(os.environ, HOME=str(cls.tmp),
                       XDG_STATE_HOME=str(cls.state),
                       XDG_CONFIG_HOME=str(cls.tmp / '.config'),
                       XDG_DATA_HOME=str(cls.tmp / '.data'),
                       XDG_CACHE_HOME=str(cls.tmp / '.cache'))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_cli(self, *args, stdin=''):
        return subprocess.run([sys.executable, str(OC_CC), *args],
                              capture_output=True, text=True, env=self.env,
                              input=stdin, timeout=30)

    def token_file(self):
        p = self.state / 'ananta-cockpit/codecompass-token.json'
        return json.loads(p.read_text()) if p.exists() else None

    def test_rejects_remote_hub_url(self):
        config = self.tmp / '.config/ananta-cockpit/codecompass.json'
        try:
            for url in ('http://evil.example:5000',
                        'http://localhost.attacker.example:5000',
                        'http://127.0.0.1.attacker.example:5000',
                        'http://127.0.0.1@attacker.example:5000',
                        'http://user:password@localhost:5000',
                        'http://localhost:invalid',
                        'http://[localhost',
                        'https://localhost:5000'):
                with self.subTest(url=url):
                    config.write_text(json.dumps({'hub_url': url}))
                    r = self.run_cli('mcp-config')
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertEqual(r.stdout, '')
        finally:
            config.write_text(
                json.dumps({'hub_url': f'http://127.0.0.1:{self.port}',
                            'server_name': 'ananta_codecompass'}))

    def test_uses_custom_xdg_config_home(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        with tempfile.TemporaryDirectory(prefix='ac-occ-config-') as config_home:
            config = Path(config_home) / 'ananta-cockpit/codecompass.json'
            config.parent.mkdir()
            config.write_text(json.dumps({'hub_url': f'http://localhost:{self.port}',
                                          'server_name': 'custom_server'}))
            env = dict(self.env, XDG_CONFIG_HOME=config_home)
            r = subprocess.run([sys.executable, str(OC_CC), 'mcp-config'],
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            server = json.loads(r.stdout)['mcp']['custom_server']
            self.assertEqual(server['url'], f'http://localhost:{self.port}/v1/mcp')

    def test_config_home_defaults_when_unset_or_empty(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        for value in (None, ''):
            with self.subTest(value=value):
                env = dict(self.env)
                if value is None:
                    env.pop('XDG_CONFIG_HOME')
                else:
                    env['XDG_CONFIG_HOME'] = value
                r = subprocess.run([sys.executable, str(OC_CC), 'mcp-config'],
                                   capture_output=True, text=True, env=env, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
                server = json.loads(r.stdout)['mcp']['ananta_codecompass']
                self.assertEqual(server['url'], f'http://127.0.0.1:{self.port}/v1/mcp')

    def test_run_signals_unavailable_hub_before_start(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        with ThreadingHTTPServer(('127.0.0.1', 0), MockHub) as stopped_server:
            port = stopped_server.server_address[1]
        config = self.tmp / '.config/ananta-cockpit/codecompass.json'
        original = config.read_text()
        config.write_text(json.dumps({'hub_url': f'http://127.0.0.1:{port}'}))
        try:
            r = self.run_cli('run')
            self.assertEqual(r.returncode, 5, r.stderr)
        finally:
            config.write_text(original)

    def test_run_rejects_failed_ping_before_start(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        MockHub.state['ping_status'] = 503
        try:
            env = dict(self.env, PATH='')
            r = subprocess.run([sys.executable, str(OC_CC), 'run'],
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 5, r.stderr)
        finally:
            MockHub.state.pop('ping_status')

    def test_login_stores_token_0600(self):
        r = self.run_cli('login', '--username', 'u', stdin='p\n\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        record = self.token_file()
        self.assertEqual(record['access_token'], 'goodtoken')
        self.assertEqual(record['refresh_token'], 'r1')
        mode = (self.state / 'ananta-cockpit/codecompass-token.json').stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)
        self.assertNotIn('goodtoken', r.stdout + r.stderr)

    def test_status_without_token_hint(self):
        (self.state / 'ananta-cockpit').mkdir(parents=True, exist_ok=True)
        tok = self.state / 'ananta-cockpit/codecompass-token.json'
        if tok.exists():
            tok.unlink()
        r = self.run_cli('status')
        self.assertEqual(r.returncode, 3)
        self.assertIn('login', r.stderr)

    def test_status_with_token(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        r = self.run_cli('status')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('Tools:      16', r.stdout)

    def test_tools_listing(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        r = self.run_cli('tools')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('codecompass.search', r.stdout)
        self.assertIn('2 Tools', r.stdout)

    def test_mcp_config_shape(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        r = self.run_cli('mcp-config')
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = json.loads(r.stdout)
        server = cfg['mcp']['ananta_codecompass']
        self.assertEqual(server['type'], 'remote')
        self.assertEqual(server['url'], f'http://127.0.0.1:{self.port}/v1/mcp')
        self.assertFalse(server['oauth'])
        self.assertEqual(server['headers']['Authorization'], 'Bearer goodtoken')

    def test_expired_token_auto_refreshes(self):
        # Token als abgelaufen markieren; Refresh-Token rotiert.
        tok = self.state / 'ananta-cockpit/codecompass-token.json'
        tok.parent.mkdir(parents=True, exist_ok=True)
        tok.write_text(json.dumps({'access_token': 'stale', 'refresh_token': 'r1',
                                   'expires_at': time.time() - 10}))
        before = MockHub.state['refresh_calls']
        r = self.run_cli('status')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(MockHub.state['refresh_calls'], before + 1)
        self.assertEqual(self.token_file()['access_token'], 'goodtoken')
        self.assertEqual(self.token_file()['refresh_token'], 'r2')

    def test_run_merges_existing_config_content(self):
        self.run_cli('login', '--username', 'u', stdin='p\n\n')
        # opencode durch ein Echo-Skript ersetzen, das die Injektion sichtbar macht.
        fake = self.tmp / 'fake-opencode'
        fake.write_text('#!/usr/bin/env bash\necho "$OPENCODE_CONFIG_CONTENT"\n')
        fake.chmod(0o755)
        env = dict(self.env, PATH=f'{self.tmp}:{os.environ["PATH"]}')
        # Ein Wrapper, der wie opencode heisst.
        (self.tmp / 'opencode').write_text('#!/usr/bin/env bash\necho "$OPENCODE_CONFIG_CONTENT"\n')
        (self.tmp / 'opencode').chmod(0o755)
        env['OPENCODE_CONFIG_CONTENT'] = '{"model": "prov/x"}'
        r = subprocess.run([sys.executable, str(OC_CC), 'run', '--', 'mcp', 'list'],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        merged = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(merged['model'], 'prov/x')
        self.assertEqual(merged['mcp']['ananta_codecompass']['headers']['Authorization'],
                         'Bearer goodtoken')


if __name__ == '__main__':
    unittest.main(verbosity=2)
