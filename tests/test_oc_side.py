#!/usr/bin/env python3
"""Tests fuer oc-side: Session-Validierung und Erfassung temporaerer Forks."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

OC_SIDE = Path(__file__).resolve().parent.parent / 'oc-side' / 'oc-side'


class FakeBin:
    """tmux- und opencode-Platzhalter, die deterministisch antworten."""

    def __init__(self, tmp: Path):
        self.bin = tmp / 'bin'
        self.bin.mkdir(parents=True, exist_ok=True)
        self.state = tmp / 'state'
        self.state.mkdir(parents=True, exist_ok=True)
        # opencode: 'session list' gibt die Session-Datei aus; delete entfernt.
        (self.bin / 'opencode').write_text(
            '#!/usr/bin/env bash\n'
            'STATE="$FAKE_STATE/sessions.txt"\n'
            'case "$1 $2" in\n'
            '  "session list") cat "$STATE" 2>/dev/null;;\n'
            '  "session delete") grep -v "^$3$" "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"; echo deleted;;\n'
            '  *) :;;\n'
            'esac\n'
        )
        # tmux: display-popup tut nichts; list ist fuer comm-Vergleiche egal.
        (self.bin / 'tmux').write_text(
            '#!/usr/bin/env bash\n'
            'if [ "$1" = "display-popup" ]; then\n'
            '  # Fork simulieren: neue Session kommt waehrend des Popups dazu.\n'
            '  echo "ses_forked01" >> "$FAKE_STATE/sessions.txt"\n'
            '  exit 0\n'
            'fi\n'
            'exit 0\n'
        )
        for f in (self.bin / 'opencode', self.bin / 'tmux'):
            f.chmod(0o755)

    def env(self):
        e = os.environ.copy()
        e['PATH'] = f'{self.bin}:{e["PATH"]}'
        e['FAKE_STATE'] = str(self.state)
        e['XDG_STATE_HOME'] = str(self.state.parent / 'xdg-state')
        e['TMUX'] = '/tmp/fake-socket,0,0'
        return e


class OcSide(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ac-ocside-'))
        self.fake = FakeBin(self.tmp)
        (self.fake.state / 'sessions.txt').write_text('ses_main01\nses_other02\n')

    def _run(self, *args):
        return subprocess.run(['bash', str(OC_SIDE), *args],
                              capture_output=True, text=True, env=self.fake.env())

    def test_rejects_bad_session_id(self):
        r = self._run('--session', 'nonsense')
        self.assertEqual(r.returncode, 2)
        self.assertIn('ses_', r.stderr)

    def test_rejects_missing_dir(self):
        r = self._run('--session', 'ses_main01', '--dir', '/nonexistent-xyz')
        self.assertNotEqual(r.returncode, 0)

    def test_records_new_forks(self):
        r = self._run('--session', 'ses_main01', '--dir', '/tmp',
                      '--model', 'xiaomi-token-plan-ams/mimo-v2.6-flash')
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.fake.env()['XDG_STATE_HOME'] + '/ananta-cockpit/side-chats.json'
        data = json.loads(Path(log).read_text())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], 'ses_forked01')
        self.assertEqual(data[0]['parent'], 'ses_main01')
        self.assertIn('created', data[0])

    def test_no_record_without_new_fork(self):
        # tmux-Popup erzeugt hier keine neue Session: sessions.txt bleibt gleich.
        (self.fake.bin / 'tmux').write_text('#!/usr/bin/env bash\nexit 0\n')
        (self.fake.bin / 'tmux').chmod(0o755)
        r = self._run('--session', 'ses_main01', '--dir', '/tmp')
        self.assertEqual(r.returncode, 0, r.stderr)
        log = Path(self.fake.env()['XDG_STATE_HOME']) / 'ananta-cockpit/side-chats.json'
        self.assertFalse(log.exists())

    def test_duplicate_record_not_duplicated(self):
        self._run('--session', 'ses_main01', '--dir', '/tmp')
        log = Path(self.fake.env()['XDG_STATE_HOME']) / 'ananta-cockpit/side-chats.json'
        data = json.loads(log.read_text())
        self.assertEqual(len(data), 1)
        # Zweiter Lauf: eine bereits erfasste ID gilt noch einmal als "neu"
        # (Session aus der Liste verschwunden, Popup meldet sie erneut).
        lines = [x for x in (self.fake.state / 'sessions.txt').read_text().splitlines()
                 if x and x != 'ses_forked01']
        (self.fake.state / 'sessions.txt').write_text('\n'.join(lines) + '\n')
        self._run('--session', 'ses_main01', '--dir', '/tmp')
        data = json.loads(log.read_text())
        self.assertEqual(len(data), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
