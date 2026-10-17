import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SelectionTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ac-select-')
        self.addCleanup(self.tmp.cleanup)
        self.socket = str(Path(self.tmp.name) / 'tmux.sock')
        self.result = Path(self.tmp.name) / 'result.json'
        self.picker_path = os.environ['PATH']
        self.tmux('new-session', '-d', '-x', '80', '-y', '24', '-s', 'test')
        self.addCleanup(lambda: self.tmux('kill-server', check=False))
        self.tmux('set-option', '-g', 'remain-on-exit', 'on')

    def tmux(self, *args, check=True):
        return subprocess.run(['tmux', '-S', self.socket, '-f', '/dev/null', *args],
                              capture_output=True, text=True, check=check)

    def capture(self):
        return self.tmux('capture-pane', '-p', '-t', 'test:0.0').stdout

    def wait_for(self, text):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            capture = self.capture()
            if text in capture:
                return capture
            time.sleep(0.02)
        self.fail(f'Terminal wartet nicht auf {text!r}: {self.capture()}')

    def start_picker(self, multiple=False, term='screen'):
        code = (f'import sys; sys.path.insert(0, {str(ROOT / "cockpit")!r}); '
                'from selection import Choice, select; '
                'choices = [Choice("alpha", "Alpha: Hauptsitzung"), '
                'Choice("beta", "Beta: Side-Sitzung")] + '
                '[Choice(str(i), "Sitzung " + str(i)) for i in range(30)]; '
                f'result = select("Sitzung waehlen", choices, {multiple!r}); '
                'import json; from pathlib import Path; '
                f'Path({str(self.result)!r}).write_text(json.dumps(result))')
        self.tmux('set-option', '-g', 'default-terminal', term)
        command = shlex.join(['env', f'PATH={self.picker_path}', sys.executable, '-c', code])
        self.tmux('respawn-pane', '-k', '-t', 'test:0.0', command)
        self.wait_for('Alpha: Hauptsitzung')

    def assert_result(self, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.result.exists():
                self.assertEqual(json.loads(self.result.read_text()), expected)
                return
            time.sleep(0.02)
        self.fail(f'Keine Auswahl zurueckgegeben: {self.capture()}')

    def fake_clipboard(self):
        target = Path(self.tmp.name) / 'clipboard.txt'
        binary = Path(self.tmp.name) / 'clip.exe'
        binary.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
                          f'Path({str(target)!r}).write_bytes(sys.stdin.buffer.read())\n')
        binary.chmod(0o755)
        self.picker_path = f'{self.tmp.name}:{os.environ["PATH"]}'
        return target

    def test_f2_copies_session_without_accepting_selection(self):
        target = self.fake_clipboard()
        self.start_picker()
        self.tmux('send-keys', '-t', 'test:0.0', 'Down', 'F2')
        self.wait_for('Kopiert: beta')
        self.assertEqual(target.read_bytes().decode('utf-16le'), 'beta')
        self.assertFalse(self.result.exists())
        self.tmux('send-keys', '-t', 'test:0.0', 'Enter')
        self.assert_result(['beta'])

    def test_right_click_copies_session_without_starting_it(self):
        target = self.fake_clipboard()
        self.start_picker(term='xterm-256color')
        self.tmux('send-keys', '-t', 'test:0.0', '-l', '\x1b[<2;5;6M\x1b[<2;5;6m')
        self.wait_for('Kopiert: beta')
        self.assertEqual(target.read_bytes().decode('utf-16le'), 'beta')
        self.assertFalse(self.result.exists())
        self.tmux('send-keys', '-t', 'test:0.0', 'Escape')
        self.assert_result([])

    def test_arrow_keys_select_session(self):
        self.start_picker()
        self.tmux('send-keys', '-t', 'test:0.0', 'Down', 'Enter')
        self.assert_result(['beta'])

    def test_click_selects_session(self):
        self.start_picker(term='xterm-256color')
        self.tmux('send-keys', '-t', 'test:0.0', '-l', '\x1b[<0;5;6M\x1b[<0;5;6m')
        self.assert_result(['beta'])

    def test_click_selects_session_with_screen_mouse_protocol(self):
        self.start_picker(term='screen')
        self.tmux('send-keys', '-t', 'test:0.0', '-l', '\x1b[M %&\x1b[M#%&')
        self.assert_result(['beta'])

    def test_mouse_and_keyboard_mark_multiple_sessions(self):
        self.start_picker(multiple=True, term='xterm-256color')
        self.tmux('send-keys', '-t', 'test:0.0', 'Space')
        self.tmux('send-keys', '-t', 'test:0.0', '-l', '\x1b[<0;5;6M\x1b[<0;5;6m')
        self.wait_for('[x] Beta: Side-Sitzung')
        self.tmux('send-keys', '-t', 'test:0.0', 'Enter')
        self.assert_result(['alpha', 'beta'])

    def test_filter_selects_matching_title(self):
        self.start_picker()
        self.tmux('send-keys', '-t', 'test:0.0', '-l', 'Side-Sitzung')
        self.wait_for('1/1 Treffer')
        self.tmux('send-keys', '-t', 'test:0.0', 'Enter')
        self.assert_result(['beta'])

    def test_no_match_can_be_cleared(self):
        self.start_picker()
        self.tmux('send-keys', '-t', 'test:0.0', '-l', 'xyz')
        self.wait_for('Keine Treffer')
        self.tmux('send-keys', '-t', 'test:0.0', 'BSpace', 'BSpace', 'BSpace', 'Down', 'Enter')
        self.assert_result(['beta'])

    def test_resize_and_end_scroll_to_last_session(self):
        self.start_picker()
        self.tmux('resize-window', '-t', 'test:0', '-x', '35', '-y', '10')
        self.tmux('send-keys', '-t', 'test:0.0', 'End')
        capture = self.wait_for('32/32 Treffer')
        self.assertIn('Sitzung 29', capture)
        self.assertTrue(all(len(line) <= 35 for line in capture.splitlines()))
        self.tmux('send-keys', '-t', 'test:0.0', 'Enter')
        self.assert_result(['29'])

    def test_escape_cancels_marked_selection(self):
        self.start_picker(multiple=True)
        self.tmux('send-keys', '-t', 'test:0.0', 'Space', 'Escape')
        self.assert_result([])


class ActionSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ac-action-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.log = self.home / 'calls.jsonl'
        script = (f'#!{sys.executable}\n'
                  'import json, os, sys\n'
                  'from pathlib import Path\n'
                  'name = Path(sys.argv[0]).name\n'
                  'if name == "opencode" and sys.argv[1:] == ["session", "list"]:\n'
                  '    print("ses_main01  Hauptprojekt\\nses_side02  Nebenprojekt")\n'
                  'elif name == "opencode" and sys.argv[1:] == ["models"]:\n'
                  '    print("provider/model-a\\nprovider/model-b")\n'
                  'else:\n'
                  '    with open(os.environ["CALL_LOG"], "a") as handle:\n'
                  '        handle.write(json.dumps([name, *sys.argv[1:]]) + "\\n")\n')
        for name in ('opencode', 'oc-side', 'oc-side-sync', 'oc-codecompass'):
            path = self.bin / name
            path.write_text(script)
            path.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / 'state'),
                        PATH=f'{self.bin}:{os.environ["PATH"]}', CALL_LOG=str(self.log))

    def action(self, name, answers):
        result = subprocess.run([sys.executable, str(ROOT / 'cockpit/actions.py'), name,
                                 str(self.home), str(ROOT / 'cockpit')],
                                input=answers, capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_side_chat_uses_selected_session_and_model(self):
        self.action('side', '1\n2\n3\n2\n1\n\n')
        self.assertEqual(self.calls(), [['oc-side', '--session', 'ses_side02', '--dir', str(self.home), '--inline',
                                         '--model', 'provider/model-b', '--codecompass']])

    def test_resume_preserves_session_and_model(self):
        log = self.home / 'state/ananta-cockpit/side-chats.json'
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps([{'id': 'ses_side02', 'parent': 'ses_main01'}]))
        self.action('side', '2\n1\n1\n1\n\n')
        self.assertEqual(self.calls(), [['oc-side', '--session', 'ses_side02', '--dir', str(self.home),
                                         '--inline', '--resume']])

    def test_resume_can_be_embedded_left_and_closes_menu(self):
        self.action('side', '2\n2\n1\n2\n')
        self.assertEqual(self.calls(), [['oc-side', '--session', 'ses_side02', '--dir', str(self.home),
                                         '--layout', 'left', '--resume']])

    def test_unrecorded_side_remains_selectable_when_other_side_chats_exist(self):
        log = self.home / 'state/ananta-cockpit/side-chats.json'
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps([{'id': 'ses_side02', 'parent': 'ses_main01'}]))
        opencode = self.bin / 'opencode'
        opencode.write_text(opencode.read_text().replace(
            'ses_side02  Nebenprojekt', 'ses_side02  Nebenprojekt\\nses_orphan03  Geschlossenes Pane'))
        self.action('side', '2\n3\n1\n1\n\n')
        self.assertEqual(self.calls(), [['oc-side', '--session', 'ses_orphan03', '--dir', str(self.home),
                                         '--inline', '--resume']])

    def test_new_side_can_be_embedded_below(self):
        self.action('side', '1\n1\n2\n1\n3\n')
        self.assertEqual(self.calls(), [['oc-side', '--session', 'ses_main01', '--dir', str(self.home),
                                         '--layout', 'below', '--model', 'provider/model-a']])

    def test_sync_excludes_main_session_and_requires_confirmation(self):
        self.action('sync', '1\n1\n2\n1\n\n')
        self.assertEqual(self.calls(), [['oc-side-sync', 'preview', '--main', 'ses_main01',
                                         '--side', 'ses_side02', '--direction', 'side-to-main']])

    def test_sync_applies_after_explicit_confirmation(self):
        self.action('sync', '1\n1\n1\n2\n\n')
        self.assertEqual([call[1] for call in self.calls()], ['preview', 'apply'])
        self.assertIn('--yes', self.calls()[1])

    def test_cancel_model_does_not_start_side_chat(self):
        self.action('side', '1\n1\n\n\n')
        self.assertEqual(self.calls(), [])

    def test_cleanup_only_deletes_marked_side_after_confirmation(self):
        log = self.home / 'state/ananta-cockpit/side-chats.json'
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps([{'id': 'ses_main01'}, {'id': 'ses_side02'}]))
        self.action('side', '3\n2\n2\n\n')
        self.assertEqual(self.calls(), [['opencode', 'session', 'delete', 'ses_side02']])
        self.assertEqual(json.loads(log.read_text()), [{'id': 'ses_main01'}])

    def test_codecompass_uses_selected_model(self):
        self.action('codecompass', '3\n2\n\n')
        self.assertEqual(self.calls(), [['oc-codecompass', 'run', '--model', 'provider/model-a']])


if __name__ == '__main__':
    unittest.main()
