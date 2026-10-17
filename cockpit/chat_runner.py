# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# Run: python3 cockpit/chat_runner.py CHAT_ID (invoked by chat_runtime).
"""Supervise the TUI and identify its saved conversation while it is alive."""
from __future__ import annotations

import json
from contextlib import ExitStack
import os
import subprocess
import sys
import time

try:
    from .chat_store import ChatRecord, ChatStore
except ImportError:
    from chat_store import ChatRecord, ChatStore


def _sessions(project: str) -> list[dict[str, str]]:
    result = subprocess.run(['opencode', 'session', 'list', '--format', 'json'], cwd=project,
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'OpenCode session listing failed')
    data = json.loads(result.stdout)
    if not isinstance(data, list):
        raise RuntimeError('OpenCode session list did not return an array')
    return data


def _identify(row: ChatRecord, before: set[str]) -> str:
    candidates = [item for item in _sessions(row['project']) if item.get('id') not in before
                  and item.get('directory') == row['project']]
    matches: list[str] = []
    for item in candidates:
        result = subprocess.run(['opencode', 'export', item['id']], cwd=row['project'],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            continue
        info = json.loads(result.stdout).get('info', {})
        if info.get('parentID', '') == row['parent_id']:
            matches.append(item['id'])
    if len(matches) > 1:
        raise RuntimeError('More than one matching conversation was created; refusing ambiguous session ID')
    return matches[0] if matches else ''


def run(chat_id: str) -> int:
    store = ChatStore()
    row = store.get(chat_id)
    command = ['oc-codecompass', 'run', '--'] if row['mcp'] else ['opencode']
    session = row['session_id'] or row['parent_id']
    if session:
        command += ['--session', session]
    if row['parent_id'] and not row['session_id']:
        command.append('--fork')
    if row['model']:
        command += ['--model', row['model']]
    os.chdir(row['project'])
    # Only one managed launch can claim a new conversation at a time.
    with ExitStack() as resources:
        with store.lock('session-discovery'):
            before = {item['id'] for item in _sessions(row['project'])} if not row['session_id'] else set()
            child = resources.enter_context(subprocess.Popen(command))
            store.update(chat_id, {'status': 'running'})
            try:
                deadline = time.monotonic() + 60
                while not row['session_id'] and child.poll() is None and time.monotonic() < deadline:
                    session_id = _identify(row, before)
                    if session_id:
                        row = store.update(chat_id, {'session_id': session_id, 'error': ''})
                        break
                    time.sleep(0.25)
                if not row['session_id']:
                    session_id = _identify(row, before)
                    if session_id:
                        row = store.update(chat_id, {'session_id': session_id})
                    else:
                        store.update(chat_id, {'error': 'Conversation ID could not be identified; automatic resume unavailable'})
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
                store.update(chat_id, {'error': f'Conversation discovery failed: {error}'})
        return _finish(store, chat_id, child.wait())


def _finish(store: ChatStore, chat_id: str, code: int) -> int:
    row = store.get(chat_id)
    if row['status'] != 'closed':
        store.update(chat_id, {'status': 'failed' if code else 'stopped',
                               'error': f'OpenCode exited with status {code}' if code else row['error']})
    print(f'\nOpenCode beendet (Exit {code}). Gespeicherter Chat bleibt verfuegbar.', flush=True)
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(run(sys.argv[1]))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        ChatStore().update(sys.argv[1], {'status': 'failed', 'error': str(error)})
        print(f'\nChat konnte nicht gestartet werden: {error}', flush=True)
        raise SystemExit(1) from error
