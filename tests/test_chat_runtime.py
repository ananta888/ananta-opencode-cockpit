"""Real tmux lifecycle checks with a persistent, non-network OpenCode stub."""
import json
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cockpit import chat_runtime as runtime


@pytest.fixture
def managed(tmp_path, monkeypatch):
    # Given an isolated tmux server and OpenCode substitute.
    binary = tmp_path / 'bin'
    binary.mkdir()
    stub = binary / 'opencode'
    stub.write_text(f'''#!{sys.executable}
import json, os, sys, time
from pathlib import Path
state=Path(os.environ['STUB_SESSIONS'])
a=sys.argv[1:]
rows=json.loads(state.read_text()) if state.exists() else []
if a[:2]==['session','list']:
 print(json.dumps(rows))
elif a[:1]==['export']:
 print(json.dumps({{'info':next(r for r in rows if r['id']==a[1])}}))
else:
 sid=a[a.index('--session')+1] if '--session' in a else ''
 if '--fork' in a or not sid:
  parent=sid
  sid='ses_'+str(os.getpid())
  rows.append({{'id':sid,'parentID':parent,'directory':os.getcwd()}})
  state.write_text(json.dumps(rows))
 Path(os.environ['STUB_PID']).write_text(str(os.getpid()))
 Path(os.environ['STUB_ARGS']).write_text(json.dumps(a))
 print('STUB_RUNNING '+sid,flush=True)
 if os.environ.get('STUB_FAIL'):
  sys.exit(7)
 while True: time.sleep(1)
''')
    stub.chmod(0o755)
    monkeypatch.setenv('PATH', f'{binary}:{os.environ["PATH"]}')
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('STUB_SESSIONS', str(tmp_path / 'sessions.json'))
    monkeypatch.setenv('STUB_PID', str(tmp_path / 'pid'))
    monkeypatch.setenv('STUB_ARGS', str(tmp_path / 'args'))
    monkeypatch.setenv('TERM', 'xterm-256color')
    socket = str(tmp_path / 'tmux.sock')
    def tmux(*args):
        return subprocess.check_output(['tmux', '-S', socket, *args], text=True).strip()
    tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'host', '-x', '120', '-y', '40')
    pane = tmux('display-message', '-p', '-t', 'host', '#{pane_id}')
    monkeypatch.setenv('TMUX', socket + ',1,0')
    monkeypatch.setenv('TMUX_PANE', pane)
    tmux('set-option', '-p', '-t', pane, '@ananta_main', '1')
    master, slave = pty.openpty()
    env = dict(os.environ)
    env.pop('TMUX', None)
    client = subprocess.Popen(['tmux', '-S', socket, 'attach-session', '-t', 'host'], stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)
    try:
        yield tmp_path, tmux, pane, client, master
    finally:
        subprocess.run(['tmux', '-S', socket, 'kill-server'], capture_output=True)
        os.close(master)
        client.wait(timeout=5)


def until(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    pytest.fail('Observable condition did not become true')


def running(tmp_path, placement='left'):
    row = runtime.launch_chat(runtime.LaunchOptions(str(tmp_path), 'ses_parent', placement=placement))
    until(lambda: runtime.ChatStore().get(row['id'])['session_id'])
    return runtime.ChatStore().get(row['id'])


def test_live_process_survives_popup_left_below_window(managed):
    # Given a live managed conversation and attached host.
    tmp_path, tmux, host, client, master = managed
    row = running(tmp_path)
    pid = int((tmp_path / 'pid').read_text())
    # When the same chat is moved through every supported surface.
    observations = []
    for placement in ('below', 'window', 'popup', 'left', 'popup', 'below'):
        runtime.move_chat(row['id'], placement)
        if placement == 'popup':
            until(lambda: len(tmux('list-clients', '-F', '#{client_session}').splitlines()) == 2)
        else:
            until(lambda: len(tmux('list-clients', '-F', '#{client_session}').splitlines()) == 1)
        os.kill(pid, 0)
        assert client.poll() is None
        assert tmux('display-message', '-p', '-t', row['pane'], '#{pane_id}') == row['pane']
        observations.append({'placement': placement, 'pid': pid, 'pane': row['pane'], 'host_attached': client.poll() is None})
    # Then the TUI PID and host client survive all transitions.
    assert len({item['pid'] for item in observations}) == 1
    print('LIFECYCLE_EVIDENCE=' + json.dumps(observations))


def test_close_preserves_session_and_resume_does_not_fork(managed):
    # Given an identified running fork.
    tmp_path, tmux, host, client, master = managed
    row = running(tmp_path)
    runtime.close_chat(row['id'])
    # When its stored conversation is resumed.
    resumed = runtime.launch_chat(runtime.LaunchOptions(str(tmp_path), row['parent_id'], resume_id=row['session_id'], placement='below'))
    until(lambda: runtime.ChatStore().get(resumed['id'])['status'] == 'running')
    until(lambda: '--fork' not in json.loads((tmp_path / 'args').read_text()))
    # Then close retained the ID and resume reused it without another fork.
    assert runtime.ChatStore().get(row['id'])['status'] == 'closed'
    assert resumed['session_id'] == row['session_id']
    assert len(json.loads((tmp_path / 'sessions.json').read_text())) == 1
    print('RESUME_EVIDENCE=' + (tmp_path / 'args').read_text())


def test_failed_child_retains_readable_pane(managed):
    # Given a stub configured to fail inside the tmux server environment.
    tmp_path, tmux, host, client, master = managed
    tmux('set-environment', '-g', 'STUB_FAIL', '1')
    # When a child exits unsuccessfully.
    row = runtime.launch_chat(runtime.LaunchOptions(str(tmp_path), 'ses_parent', placement='below'))
    until(lambda: runtime.ChatStore().get(row['id'])['status'] == 'failed')
    # Then its dead pane retains the diagnostic and session identity.
    screen = tmux('capture-pane', '-p', '-t', row['pane'])
    assert 'Exit 7' in screen
    assert runtime.ChatStore().get(row['id'])['session_id']
    print('FAILURE_SCREEN=' + repr(screen))


def test_current_chat_from_docked_pane_and_rename(managed, monkeypatch):
    # Given a docked managed conversation.
    tmp_path, tmux, host, client, master = managed
    row = running(tmp_path)
    monkeypatch.setenv('TMUX_PANE', row['pane'])
    # When renamed from the chat's own context.
    runtime.rename_chat(row['id'], 'Investigate issue')
    # Then identity and host context remain available inside the chat.
    assert runtime.current_chat()['title'] == 'Investigate issue'
    assert runtime.host_context()['host_main'] == host


def test_second_chat_starts_while_first_tui_stays_alive(managed):
    # Given a first chat whose ID has already been identified.
    tmp_path, tmux, host, client, master = managed
    first = running(tmp_path)
    first_pid = int((tmp_path / 'pid').read_text())
    # When a second chat is launched while the first remains interactive.
    second = running(tmp_path, 'below')
    # Then discovery releases its lock and records distinct forks.
    os.kill(first_pid, 0)
    assert first['session_id'] != second['session_id']
    assert first['pane'] != second['pane']
    print('CONCURRENT_IDS=' + json.dumps([first['session_id'], second['session_id']]))


def test_main_adoption_does_not_replace_host_process(managed):
    # Given the existing host main pane.
    tmp_path, tmux, host, client, master = managed
    pid = tmux('display-message', '-p', '-t', host, '#{pane_pid}')
    # When the main conversation is adopted into the registry.
    row = runtime.adopt_main(str(tmp_path), 'ses_existing', host)
    # Then adoption only adds metadata and preserves the host process.
    assert row['kind'] == 'main'
    assert row['session_id'] == 'ses_existing'
    assert tmux('display-message', '-p', '-t', host, '#{pane_pid}') == pid
    assert runtime.current_chat()['id'] == row['id']
    print('ADOPTION_EVIDENCE=' + json.dumps(row))


def test_new_main_starts_without_fork_or_session_flags(managed):
    # Given a host without a managed main chat.
    tmp_path, tmux, host, client, master = managed
    # When a new main conversation is started.
    row = runtime.launch_chat(runtime.LaunchOptions(str(tmp_path), placement='window'))
    until(lambda: runtime.ChatStore().get(row['id'])['session_id'])
    # Then OpenCode starts a fresh conversation and its ID is saved live.
    assert json.loads((tmp_path / 'args').read_text()) == []
    assert runtime.ChatStore().get(row['id'])['kind'] == 'main'
    print('NEW_MAIN_EVIDENCE=' + json.dumps(runtime.ChatStore().get(row['id'])))


def test_discovery_filters_unrelated_conversation_by_parent(managed):
    # Given two newly listed conversations in the same directory.
    from cockpit.chat_runner import _identify
    tmp_path, tmux, host, client, master = managed
    row = runtime.adopt_main(str(tmp_path), 'ses_existing', host)
    row['parent_id'] = 'ses_parent'
    (tmp_path / 'sessions.json').write_text(json.dumps([
        {'id': 'ses_unrelated', 'parentID': 'ses_other', 'directory': str(tmp_path)},
        {'id': 'ses_expected', 'parentID': 'ses_parent', 'directory': str(tmp_path)},
    ]))
    # When discovery exports candidates to inspect their actual parent.
    found = _identify(row, set())
    # Then only the verified fork is selected.
    assert found == 'ses_expected'
    print('PARENT_MATCH_EVIDENCE=' + found)
