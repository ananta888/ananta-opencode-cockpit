import fcntl
import json
import os
import pty
import select
import shlex
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SidePopup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ac-side-popup-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.sessions = self.home / 'sessions'
        self.sessions.write_text('ses_main01\n')
        self.opencode = self.bin / 'opencode'
        self.opencode.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'path = Path(os.environ["SESSION_FILE"])\n'
            'if sys.argv[1:] == ["session", "list"]:\n'
            '    print(path.read_text())\n'
            'elif sys.argv[1:] == ["models"]:\n'
            '    print("provider/test-model")\n'
            'else:\n'
            '    Path(os.environ["RUN_ARGS"]).write_text(json.dumps(sys.argv[1:]))\n'
            '    if "--fork" in sys.argv:\n'
            '        path.write_text("ses_main01\\nses_fork01\\n")\n'
            '    print("SIDE_RUNNING" if "--fork" in sys.argv else "SIDE_RESUMED", flush=True)\n'
            '    input()\n')
        self.opencode.chmod(0o755)
        side_cli = self.bin / 'oc-side'
        side_cli.write_bytes((ROOT / 'oc-side/oc-side').read_bytes())
        side_cli.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_STATE_HOME=str(self.home / 'state'),
                        PATH=f'{self.bin}:{os.environ["PATH"]}',
                        SESSION_FILE=str(self.sessions), RUN_ARGS=str(self.home / 'args.json'),
                        TERM='xterm-256color')
        self.tmux = ['tmux', '-S', str(self.home / 'tmux.sock'), '-f', '/dev/null']
        subprocess.run([*self.tmux, 'new-session', '-d', '-x', '100', '-y', '32',
                        '-s', 'side-test'], env=self.env, check=True)
        self.addCleanup(lambda: subprocess.run([*self.tmux, 'kill-server'],
                                               capture_output=True, check=False))
        self.main = subprocess.check_output([*self.tmux, 'display-message', '-p', '#{pane_id}'],
                                            env=self.env, text=True).strip()
        subprocess.run([*self.tmux, 'set-option', '-p', '-t', self.main, '@ananta_main', '1'], check=True)
        self.master, slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 100, 0, 0))
        self.client = subprocess.Popen([*self.tmux, 'attach-session', '-t', 'side-test'],
                                       stdin=slave, stdout=slave, stderr=slave, env=self.env)
        os.close(slave)
        self.addCleanup(self.stop, self.client)
        self.output = b''
        self.wait_for(b'side-test')

    def stop(self, process):
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)

    def wait_for(self, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master], [], [], max(0, deadline - time.monotonic()))
            if ready:
                self.output += os.read(self.master, 65536)
                if expected in self.output:
                    self.output = b''
                    return
        self.fail(f'Popup zeigt {expected!r} nicht: {self.output[-1800:]!r}')

    def launch(self, resume=False, layout='popup'):
        command = shlex.join([sys.executable, str(ROOT / 'cockpit/actions.py'),
                              'side', str(self.home), str(ROOT / 'cockpit')])
        self.popup = subprocess.Popen([*self.tmux, 'display-popup', '-E', '-t', 'side-test',
                                      '-w', '90%', '-h', '90%', command], env=self.env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop, self.popup)
        self.wait_for(b'oeffnen')
        os.write(self.master, b'\x1bOB\r' if resume else b'\r')
        titles = [b'Bestehenden Side-Chat fortsetzen'] if resume else [b'Hauptsitzung', b'Modell waehlen']
        for title in [*titles, b'CodeCompass-MCP']:
            self.wait_for(title)
            os.write(self.master, b'\r')
        self.wait_for(b'Platzierung')
        down = {'popup': 0, 'left': 1, 'below': 2}[layout]
        os.write(self.master, b'\x1bOB' * down + b'\r')

    def test_cockpit_starts_side_chat_inside_existing_popup(self):
        self.launch()
        self.wait_for(b'SIDE_RUNNING')
        self.assertIsNone(self.popup.poll())
        self.assertIn('ses_fork01', self.sessions.read_text())
        os.write(self.master, b'\r')
        self.wait_for(b'Enter zum Schliessen')
        log = self.home / 'state/ananta-cockpit/side-chats.json'
        self.assertIn('ses_fork01', log.read_text())

    def test_failed_side_chat_keeps_error_visible_in_popup(self):
        self.opencode.write_text(self.opencode.read_text().replace('    input()', '    raise SystemExit(7)'))
        self.launch()
        self.wait_for(b'Exit 7')
        self.assertIsNone(self.popup.poll())

    def geometry(self):
        output = subprocess.check_output([*self.tmux, 'list-panes', '-t', 'side-test', '-F',
                                           '#{pane_id}|#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}'],
                                          text=True)
        return {parts[0]: tuple(map(int, parts[1:])) for line in output.splitlines()
                if (parts := line.split('|'))}

    def test_left_pane_splits_main_instead_of_sidebar(self):
        subprocess.run([*self.tmux, 'set-option', '-pu', '-t', self.main, '@ananta_main'], check=True)
        sidebar = subprocess.check_output([*self.tmux, 'split-window', '-hd', '-l', '20',
                                           '-t', self.main, '-P', '-F', '#{pane_id}'], text=True).strip()
        subprocess.run([*self.tmux, 'set-option', '-p', '-t', sidebar, '@ananta_cockpit', '1'], check=True)
        subprocess.run([*self.tmux, 'select-pane', '-t', sidebar], check=True)
        before = self.geometry()
        self.launch(layout='left')
        self.wait_for(b'SIDE_RUNNING')
        self.assertEqual(self.popup.wait(timeout=5), 0)
        after = self.geometry()
        side = next(pane for pane in after if pane not in before)
        self.assertLess(after[side][0], after[self.main][0])
        self.assertEqual(after[side][1], after[self.main][1])
        self.assertEqual(after[sidebar], before[sidebar])
        marker = subprocess.check_output([*self.tmux, 'show-options', '-pv', '-t', self.main,
                                          '@ananta_main'], text=True).strip()
        self.assertEqual(marker, '1')

    def test_below_pane_can_close_and_resume_without_another_fork(self):
        self.launch(layout='below')
        self.wait_for(b'SIDE_RUNNING')
        self.assertEqual(self.popup.wait(timeout=5), 0)
        panes = self.geometry()
        side = next(pane for pane in panes if pane != self.main)
        self.assertGreater(panes[side][1], panes[self.main][1])
        self.assertEqual(panes[side][0], panes[self.main][0])
        os.write(self.master, b'\r')
        log = self.home / 'state/ananta-cockpit/side-chats.json'
        deadline = time.monotonic() + 5
        while not log.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIn('ses_fork01', log.read_text())
        before = self.sessions.read_text()
        self.launch(resume=True)
        self.wait_for(b'SIDE_RESUMED')
        args = json.loads((self.home / 'args.json').read_text())
        self.assertEqual(args, ['--session', 'ses_fork01'])
        self.assertEqual(self.sessions.read_text(), before)


if __name__ == '__main__':
    unittest.main()
