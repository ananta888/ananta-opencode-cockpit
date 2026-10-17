#!/usr/bin/env python3
"""Catalog routing and real native tmux menu keyboard tests."""
import json
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cockpit'))
import catalog
import menus


class MenuTests(unittest.TestCase):
    def test_routes_have_unique_keys_and_reachable_actions(self):
        for menu in catalog.MENUS:
            with self.subTest(menu=menu):
                entries = (*catalog.actions_for(menu), *catalog.submenus_for(menu))
                keys = [entry.key for entry in entries]
                self.assertEqual(len(keys), len(set(keys)))
                for action in catalog.actions_for(menu):
                    route = catalog.shortcut(action.id, 'C-a').split()
                    self.assertEqual(route[:2], ['C-a', 'g'])
                    self.assertEqual(route[-1], action.key)

    def test_shell_arguments_roundtrip_user_values(self):
        project = "/tmp/space ' quote ; $(touch nope) #{session_name}"
        chat = "chat ' ; $(false)"
        command = menus.dispatch_command('chat-resume', project, chat, ROOT / 'cockpit')
        self.assertEqual(shlex.split(command), ['python3', str(ROOT / 'cockpit/app.py'),
                                              'dispatch', 'chat-resume', project, chat])

    def test_title_formats_are_literal(self):
        argv = menus.build_menu('chat', '/tmp', '#{session_name} #[fg=red]\nhello')
        self.assertIn('##{session_name} ##[fg=red] hello', argv[argv.index('-T') + 1])

    def test_invalid_menu_cli_fails(self):
        result = subprocess.run([sys.executable, str(ROOT / 'cockpit/menus.py'),
                                 'unknown', '/tmp'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_native_menu_selects_action_with_literal_arguments(self):
        with tempfile.TemporaryDirectory(prefix='ananta-menu-') as directory:
            work = Path(directory)
            socket = str(work / 'socket')
            output = work / 'dispatch.json'
            (work / 'app.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                f'Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))\n')
            child, terminal = pty.fork()
            if child == 0:
                os.environ['TERM'] = 'xterm-256color'
                os.execvp('tmux', ['tmux', '-S', socket, '-f', '/dev/null',
                                   'new-session', '-s', 'menu-test', '/bin/sh'])
            captured = bytearray()
            try:
                deadline = time.monotonic() + 8
                while b'menu-test' not in captured and time.monotonic() < deadline:
                    if select.select([terminal], [], [], 0.1)[0]:
                        captured.extend(os.read(terminal, 65536))
                project = "/tmp/space ' quote ; $(false) #{session_name}"
                chat = "id ' quote #{session_name}"
                argv = menus.build_menu('chat', project, chat, 'C-a', work)
                menu = subprocess.Popen(['tmux', '-S', socket, *argv[1:]],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while b'Neuer Chat' not in captured and time.monotonic() < deadline:
                    if select.select([terminal], [], [], 0.1)[0]:
                        captured.extend(os.read(terminal, 65536))
                self.assertIn(b'Neuer Chat', captured)
                os.write(terminal, b'n')
                stdout, stderr = menu.communicate(timeout=5)
                self.assertEqual(menu.returncode, 0, stderr.decode())
                while not output.exists() and time.monotonic() < deadline:
                    if select.select([terminal], [], [], 0.05)[0]:
                        captured.extend(os.read(terminal, 65536))
                self.assertTrue(output.exists(), 'native menu did not dispatch')
                self.assertEqual(json.loads(output.read_text()),
                                 ['dispatch', 'chat-new', project, chat])
                evidence = os.environ.get('MENU_EVIDENCE_DIR')
                if evidence:
                    target = Path(evidence)
                    target.mkdir(parents=True, exist_ok=True)
                    (target / 'native-menu.ansi').write_bytes(captured)
                    (target / 'native-dispatch.json').write_text(output.read_text())
            finally:
                subprocess.run(['tmux', '-S', socket, 'kill-server'], capture_output=True)
                os.close(terminal)
                os.waitpid(child, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
