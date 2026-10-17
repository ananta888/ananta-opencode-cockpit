#!/usr/bin/env python3
"""Tests fuer slim-plan (planctl.py): Zustandsmaschine ohne LLM-Aufrufe."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLANCTL = Path(__file__).resolve().parent.parent / 'slim-router' / 'planctl.py'


def run(*args, cwd):
    return subprocess.run([sys.executable, str(PLANCTL), *args],
                          capture_output=True, text=True, cwd=cwd)


class Planctl(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='ac-plan-'))

    def test_init_add_next_done_status(self):
        r = run('init', 'Cockpit stabilisieren', cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.dir / '.opencode/slim-context/state.json').exists())
        # Zweites Init darf nichts ueberschreiben
        r = run('init', 'Andere Mission', cwd=self.dir)
        self.assertEqual(r.returncode, 0)
        state = json.loads((self.dir / '.opencode/slim-context/state.json').read_text())
        self.assertEqual(state['objective'], 'Cockpit stabilisieren')

        r = run('add', 'Installation fixen', '--description', 'Pfade',
                '--acceptance', 'install.sh laeuft', cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run('add', 'Tests schreiben', '--after', '001', cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)

        r = run('next', cwd=self.dir)
        self.assertIn('Installation fixen', r.stdout)
        # Abhaengige Aufgabe darf nicht naechste sein
        self.assertNotIn('Tests schreiben', r.stdout)

        r = run('next', '--activate', cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)

        r = run('done', '001', '--evidence', 'unittest gruen', cwd=self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)

        r = run('next', cwd=self.dir)
        self.assertIn('Tests schreiben', r.stdout)

        r = run('status', cwd=self.dir)
        self.assertIn('done', r.stdout)
        self.assertIn('Cockpit stabilisieren', r.stdout)

        r = run('brief', cwd=self.dir)
        self.assertIn('Work checkpoint', r.stdout)
        self.assertIn('not proof of task completion', r.stdout)

    def test_done_requires_evidence(self):
        run('init', 'x', cwd=self.dir)
        run('add', 'Task', cwd=self.dir)
        r = run('done', '001', cwd=self.dir)
        self.assertNotEqual(r.returncode, 0)

    def test_unknown_dependency_rejected(self):
        run('init', 'x', cwd=self.dir)
        r = run('add', 'Task', '--after', '999', cwd=self.dir)
        self.assertNotEqual(r.returncode, 0)

    def test_atomic_write_leaves_no_tmp(self):
        run('init', 'x', cwd=self.dir)
        run('add', 'Task', cwd=self.dir)
        leftovers = list((self.dir / '.opencode/slim-context').rglob('*.tmp'))
        self.assertEqual(leftovers, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
