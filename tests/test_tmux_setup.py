#!/usr/bin/env python3
"""Unit-/Integrationstests fuer tmux_setup.py (unittest, keine externen Abhaengigkeiten)."""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'cockpit'))
import tmux_setup  # noqa: E402


class FakeTmux:
    """Ersetzt das tmux-Binary durch ein Drehbuch (scripted responses)."""

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.calls = tmpdir / 'calls.log'
        self.responses = tmpdir / 'responses'
        self.responses.mkdir(parents=True, exist_ok=True)
        self.calls.write_text('')
        self.bin = tmpdir / 'bin'
        self.bin.mkdir(exist_ok=True)
        fake = self.bin / 'tmux'
        fake.write_text(
            '#!/usr/bin/env python3\n'
            'import os,sys\n'
            'log=os.environ["FAKE_TMUX_LOG"]\n'
            'open(log,"a").write(" ".join(sys.argv[1:])+"\\n")\n'
            'args=sys.argv[1:]\n'
            'key="_".join(args[:2]) if len(args)>=2 else (args[0] if args else "none")\n'
            'resp=os.path.join(os.environ["FAKE_TMUX_RESP"], key)\n'
            'if os.path.exists(resp):\n'
            '    sys.stdout.write(open(resp).read())\n'
            'rc=os.path.join(os.environ["FAKE_TMUX_RESP"], key+".rc")\n'
            'sys.exit(int(open(rc).read()) if os.path.exists(rc) else 0)\n'
        )
        fake.chmod(0o755)

    def set(self, key, out='', rc=0):
        (self.responses / key).write_text(out)
        (self.responses / (key + '.rc')).write_text(str(rc))

    @contextlib.contextmanager
    def activated(self):
        old = os.environ.copy()
        os.environ['PATH'] = f'{self.bin}:{old["PATH"]}'
        os.environ['FAKE_TMUX_LOG'] = str(self.calls)
        os.environ['FAKE_TMUX_RESP'] = str(self.responses)
        try:
            yield self
        finally:
            os.environ.clear()
            os.environ.update(old)

    def env(self):
        e = os.environ.copy()
        e['PATH'] = f'{self.bin}:{e["PATH"]}'
        e['FAKE_TMUX_LOG'] = str(self.calls)
        e['FAKE_TMUX_RESP'] = str(self.responses)
        return e


class TmuxSetupUnit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ac-test-'))
        self.fake = FakeTmux(self.tmp)

    def test_pane_exists_true(self):
        self.fake.set('list-panes_-a', '%0\n%1\n')
        with self.fake.activated():
            self.assertTrue(tmux_setup.pane_exists('%1'))

    def test_pane_exists_false(self):
        self.fake.set('list-panes_-a', '%0\n')
        with self.fake.activated():
            self.assertFalse(tmux_setup.pane_exists('%2'))

    def test_pane_exists_empty(self):
        self.fake.set('list-panes_-a', '', rc=1)
        with self.fake.activated():
            self.assertFalse(tmux_setup.pane_exists(''))

    def test_find_control_pane_by_marker(self):
        self.fake.set('list-panes_-F', '%0:::0:::bash\n%1:::1:::python3\n')
        with self.fake.activated():
            self.assertEqual(tmux_setup.find_control_pane(), '%1')

    def test_find_control_pane_by_legacy_title(self):
        self.fake.set('list-panes_-F', '%3:::0:::ANANTA CONTROL\n')
        with self.fake.activated():
            self.assertEqual(tmux_setup.find_control_pane(), '%3')

    def test_find_control_pane_none(self):
        self.fake.set('list-panes_-F', '%0:::0:::bash\n')
        with self.fake.activated():
            self.assertIsNone(tmux_setup.find_control_pane())

    def test_missing_tmux_binary_reports_friendly_error(self):
        e = os.environ.copy()
        e['PATH'] = str(self.tmp)  # kein tmux auffindbar
        r = subprocess.run(
            [sys.executable, str(ROOT / 'cockpit' / 'tmux_setup.py'), 'start', str(ROOT),
             '/tmp', str(self.tmp / 'state')],
            capture_output=True, text=True, env=e)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('tmux nicht gefunden', r.stderr)


class TmuxSetupIntegration(unittest.TestCase):
    """Echter tmux-Server (detached Session) – prueft Start/Idempotenz/Stop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ac-tmux-test-')
        self.socket = str(Path(self.tmp.name) / 'tmux.sock')
        self.session = 'ac-unittest'
        self.old_tmux = os.environ.get('TMUX')
        subprocess.run(['tmux', '-S', self.socket, '-f', '/dev/null', 'new-session',
                        '-d', '-s', self.session, '-c', '/tmp'], check=True)
        os.environ['TMUX'] = f'{self.socket},0,0'
        self.state = Path(self.tmp.name) / 'state'
        self.project = str(Path(self.tmp.name) / 'project')
        Path(self.project).mkdir()
        self.env = os.environ.copy()

    def tearDown(self):
        subprocess.run(['tmux', '-S', self.socket, 'kill-server'], capture_output=True)
        if self.old_tmux is None:
            os.environ.pop('TMUX', None)
        else:
            os.environ['TMUX'] = self.old_tmux
        self.tmp.cleanup()

    def test_restores_exact_options_and_bindings(self):
        # Given custom local formats, empty strings, and existing bindings.
        tmux_setup.tm('set-option', '-t', self.session, 'status-left', '')
        tmux_setup.tm('set-option', '-t', self.session, 'status-format[0]', 'custom #{session_name}')
        tmux_setup.tm('set-option', '-t', self.session, 'status-format[2]', 'third row')
        tmux_setup.tm('set-option', '-t', self.session, 'prefix', 'C-a')
        tmux_setup.tm('bind-key', '-T', 'prefix', 'g', 'display-message', 'original g')
        tmux_setup.tm('bind-key', '-T', 'ananta', 'x', 'display-message', 'original table')
        before_options = tmux_setup.tm('show-options', '-t', self.session)
        before_bindings = tmux_setup.tm('list-keys')
        # When start is repeated and stopped.
        tmux_setup.start(str(ROOT / 'cockpit'), self.project, self.state)
        active_status = tmux_setup.tm('show-options', '-v', '-t', self.session, 'status')
        active_format = tmux_setup.tm('show-options', '-v', '-t', self.session, 'status-format[0]')
        tmux_setup.start(str(ROOT / 'cockpit'), self.project, self.state)
        tmux_setup.stop(str(ROOT / 'cockpit'), self.project, self.state)
        after_options = tmux_setup.tm('show-options', '-t', self.session)
        after_bindings = tmux_setup.tm('list-keys')
        # Then exact local options and all bindings are restored.
        self.assertEqual(active_status, '2')
        self.assertIn('C-a g', active_format)
        self.assertEqual(after_options, before_options)
        self.assertEqual(after_bindings, before_bindings)
        evidence = os.environ.get('STATUS_EVIDENCE_DIR')
        if evidence:
            target = Path(evidence)
            target.mkdir(parents=True, exist_ok=True)
            (target / 'restoration.json').write_text(json.dumps({
                'before_options': before_options, 'after_options': after_options,
                'before_bindings': before_bindings, 'after_bindings': after_bindings,
                'active_status': active_status, 'active_format': active_format}, indent=2))

    def _panes(self):
        out = subprocess.check_output(
            ['tmux', 'list-panes', '-t', self.session, '-F',
             '#{pane_id}:::#{@ananta_cockpit}'], text=True)
        return out.strip().splitlines()

    def _control_count(self):
        return len([p for p in self._panes() if p.endswith(':::1')])

    def test_start_idempotent_and_stop(self):
        script = str(ROOT / 'cockpit' / 'tmux_setup.py')
        rootdir = str(ROOT / 'cockpit')
        proj, state = self.project, str(self.state)
        r = subprocess.run([sys.executable, script, 'start', rootdir, proj, state],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._control_count(), 1, self._panes())
        # Idempotenz: zweiter Start erzeugt kein weiteres Pane
        r2 = subprocess.run([sys.executable, script, 'start', rootdir, proj, state],
                            capture_output=True, text=True, env=self.env)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn('bereits', r2.stdout)
        self.assertEqual(self._control_count(), 1)
        # Stop entfernt das Pane und stellt Optionen wieder her
        r3 = subprocess.run([sys.executable, script, 'stop', rootdir, proj, state],
                            capture_output=True, text=True, env=self.env)
        self.assertEqual(r3.returncode, 0, r3.stderr)
        self.assertEqual(self._control_count(), 0)
        left = subprocess.check_output(
            ['tmux', 'show-options', '-t', self.session, 'status-left'], text=True)
        self.assertNotIn('ANANTA', left)
        # Erneuter Start nach Stop funktioniert
        r4 = subprocess.run([sys.executable, script, 'start', rootdir, proj, state],
                            capture_output=True, text=True, env=self.env)
        self.assertEqual(r4.returncode, 0, r4.stderr)
        self.assertEqual(self._control_count(), 1)

    def test_start_with_missing_sidebar_recovers(self):
        """Fehlt cockpit/sidebar, darf kein totes Pane uebrig bleiben."""
        broken_root = Path(tempfile.mkdtemp(prefix='ac-broken-'))
        (broken_root / 'tmux_setup.py').write_text((ROOT / 'cockpit' / 'tmux_setup.py').read_text())
        script = str(ROOT / 'cockpit' / 'tmux_setup.py')
        r = subprocess.run([sys.executable, script, 'start', str(broken_root),
                            self.project, str(self.state)],
                           capture_output=True, text=True, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Fehler', r.stderr)
        self.assertIn('CONTROL-Pane', r.stderr)
        time.sleep(0.3)
        self.assertEqual(self._control_count(), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
