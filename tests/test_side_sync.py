#!/usr/bin/env python3
"""Tests fuer oc-side-sync (side-sync.py): Cursor-Logik, Duplikatschutz, Bestaetigung."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SIDE_SYNC = Path(__file__).resolve().parent.parent / 'oc-side-sync' / 'side-sync.py'
spec = importlib.util.spec_from_file_location('side_sync', SIDE_SYNC)
side_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(side_sync)


class MsgFactory:
    @staticmethod
    def user(id_, text):
        return {'info': {'role': 'user', 'id': id_}, 'parts': [{'type': 'text', 'text': text}]}

    @staticmethod
    def assistant(id_, text):
        return {'info': {'role': 'assistant', 'id': id_}, 'parts': [{'type': 'text', 'text': text}]}

    @staticmethod
    def tool(id_, text):
        return {'info': {'role': 'assistant', 'id': id_},
                'parts': [{'type': 'tool', 'text': text, 'state': {'status': 'completed'}}]}

    @staticmethod
    def synced(id_, text):
        return {'info': {'role': 'user', 'id': id_},
                'parts': [{'type': 'text', 'text': '[SIDE-SYNC from ses_a to ses_b] ' + text}]}


class MockAPI:
    def __init__(self, messages=None, busy=False):
        self._messages = messages or {}
        self._busy = busy
        self.notes = []

    def messages(self, id_):
        return self._messages.get(id_, [])

    def status(self):
        return {'ses_dst': {'type': 'busy' if self._busy else 'idle'}}

    def post_note(self, id_, text):
        self.notes.append((id_, text))


class Extract(unittest.TestCase):
    def test_extracts_user_and_assistant_text(self):
        m = MsgFactory.user('m1', 'hello world')
        self.assertEqual(side_sync.extract(m),
                         {'id': 'm1', 'role': 'user', 'text': 'hello world'})

    def test_skips_sync_markers(self):
        m = MsgFactory.synced('m2', 'imported')
        self.assertIsNone(side_sync.extract(m))

    def test_skips_pure_tool_parts(self):
        m = MsgFactory.tool('m3', 'huge binary output')
        self.assertIsNone(side_sync.extract(m))

    def test_skips_empty(self):
        m = {'info': {'role': 'user', 'id': 'm4'}, 'parts': []}
        self.assertIsNone(side_sync.extract(m))


class Payload(unittest.TestCase):
    def test_returns_only_new_messages(self):
        api = MockAPI({'ses_a': [
            MsgFactory.user('m1', 'old'), MsgFactory.assistant('m2', 'answer'),
            MsgFactory.user('m3', 'new question'),
        ]})
        rows, cursor = side_sync.payload(api, 'ses_a', 'm2')
        self.assertEqual([r['id'] for r in rows], ['m3'])
        self.assertEqual(cursor, 'm3')

    def test_refuses_when_cursor_unknown(self):
        api = MockAPI({'ses_a': [MsgFactory.user('m1', 'x')]})
        with self.assertRaises(RuntimeError):
            side_sync.payload(api, 'ses_a', 'm_missing')

    def test_cursor_stays_when_no_new(self):
        api = MockAPI({'ses_a': [MsgFactory.user('m1', 'x')]})
        rows, cursor = side_sync.payload(api, 'ses_a', 'm1')
        self.assertEqual(rows, [])
        self.assertEqual(cursor, 'm1')

    def test_all_messages_without_cursor(self):
        api = MockAPI({'ses_a': [
            MsgFactory.user('m1', 'a'), MsgFactory.assistant('m2', 'b')]})
        rows, cursor = side_sync.payload(api, 'ses_a', None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(cursor, 'm2')


class NoteBuilder(unittest.TestCase):
    def test_note_has_warning_and_truncation(self):
        rows = [{'id': 'm1', 'role': 'user', 'text': 'x' * 50}]
        note = side_sync.make_note(rows, 'ses_a', 'ses_b', limit=10)
        self.assertIn('[SIDE-SYNC from ses_a to ses_b]', note)
        self.assertIn('Do not replay', note)
        self.assertIn('[TRUNCATED', note)


class StateFiles(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 's.json'
            s = {'seen': {'main-to-side': 'm9'}, 'pending': {}}
            side_sync.save(p, s)
            self.assertEqual(side_sync.readstate(p)['seen']['main-to-side'], 'm9')

    def test_statefile_is_stable_per_pair(self):
        a = side_sync.statefile('ses_1|ses_2')
        b = side_sync.statefile('ses_1|ses_2')
        c = side_sync.statefile('ses_2|ses_1')
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class CliValidation(unittest.TestCase):
    def _run(self, argv):
        import subprocess
        return subprocess.run(
            [sys.executable, str(SIDE_SYNC), *argv],
            capture_output=True, text=True)

    def test_rejects_non_session_ids(self):
        r = self._run(['preview', '--main', 'foo', '--side', 'ses_abc'])
        self.assertNotEqual(r.returncode, 0)

    def test_rejects_identical_sessions(self):
        r = self._run(['preview', '--main', 'ses_abc', '--side', 'ses_abc'])
        self.assertNotEqual(r.returncode, 0)

    def test_apply_requires_yes(self):
        r = self._run(['apply', '--main', 'ses_abc1', '--side', 'ses_abc2'])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--yes', (r.stderr or '') + (r.stdout or ''))

    def test_reset_requires_yes(self):
        r = self._run(['reset', '--main', 'ses_abc1', '--side', 'ses_abc2'])
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
