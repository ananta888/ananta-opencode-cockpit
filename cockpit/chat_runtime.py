"""Move live OpenCode panes without restarting their processes."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

try:
    from .chat_store import ChatRecord, ChatStore
except ImportError:
    from chat_store import ChatRecord, ChatStore


class ChatRuntimeError(RuntimeError):
    """A managed chat action failed; suitable for display in the UI."""


class HostContext(TypedDict):
    socket: str
    host_session: str
    host_main: str


@dataclass(frozen=True, slots=True)
class LaunchOptions:
    project: str
    parent_id: str = ''
    model: str | None = None
    mcp: bool = False
    resume_id: str | None = None
    placement: str = 'popup'


def _tmux(socket: str, *args: str) -> str:
    try:
        result = subprocess.run(['tmux', '-S', socket, *args], capture_output=True, text=True, check=False)
    except OSError as error:
        raise ChatRuntimeError(str(error)) from error
    if result.returncode:
        raise ChatRuntimeError(result.stderr.strip() or 'tmux command failed')
    return result.stdout.strip()


def _socket() -> str:
    result = subprocess.run(['tmux', 'display-message', '-p', '#{socket_path}'], capture_output=True, text=True, check=False)
    if result.returncode or not result.stdout.strip():
        raise ChatRuntimeError('This action requires a running tmux session')
    return result.stdout.strip()


def list_chats(project: str | None = None) -> list[ChatRecord]:
    return [row for row in ChatStore().list() if project is None or row['project'] == project]


def current_chat() -> ChatRecord | None:
    pane = os.environ.get('TMUX_PANE', '')
    return next((row for row in list_chats() if row['pane'] == pane and row['status'] != 'closed'), None)


def host_context() -> HostContext:
    current = current_chat()
    if current:
        return {key: current[key] for key in ('socket', 'host_session', 'host_main')}
    socket = _socket()
    pane = os.environ.get('TMUX_PANE', '')
    session = _tmux(socket, 'display-message', '-p', '-t', pane, '#{session_id}')
    rows = _tmux(socket, 'list-panes', '-t', session, '-F', '#{pane_id}|#{@ananta_main}|#{@ananta_cockpit}').splitlines()
    main = next((row.split('|')[0] for row in rows if row.split('|')[1] == '1'), '')
    main = main or next((row.split('|')[0] for row in rows if row.split('|')[2] != '1'), pane)
    return HostContext(socket=socket, host_session=session, host_main=main)


def _record(options: LaunchOptions) -> ChatRecord:
    context = host_context()
    chat_id = uuid.uuid4().hex
    return ChatRecord(id=chat_id, title='Side-Chat' if options.parent_id else 'Hauptchat',
                      project=str(Path(options.project).resolve()), parent_id=options.parent_id or '',
                      session_id=options.resume_id or '', pane='', holding_session=f'ac-chat-{chat_id}',
                      **context, model=options.model or '', mcp=options.mcp, status='starting',
                      placement=options.placement, kind='side' if options.parent_id else 'main', error='')


def launch_chat(options: LaunchOptions) -> ChatRecord:
    if options.placement not in ('popup', 'left', 'below', 'window'):
        raise ChatRuntimeError(f'Unknown placement: {options.placement}')
    store = ChatStore()
    row = store.save(_record(options))
    command = shlex.join([sys.executable, str(Path(__file__).with_name('chat_runner.py')), row['id']])
    # An idle shell allows remain-on-exit and metadata to be installed before startup.
    try:
        pane = _tmux(row['socket'], 'new-session', '-d', '-s', row['holding_session'], '-c', row['project'], '-P', '-F', '#{pane_id}', 'sleep 86400')
        row = store.update(row['id'], {'pane': pane})
        _tmux(row['socket'], 'set-option', '-p', '-t', pane, 'remain-on-exit', 'on')
        _tmux(row['socket'], 'set-option', '-p', '-t', pane, '@ananta_chat', row['id'])
        _tmux(row['socket'], 'set-option', '-t', row['holding_session'], 'detach-on-destroy', 'on')
        _tmux(row['socket'], 'respawn-pane', '-k', '-t', pane, command)
        return move_chat(row['id'], options.placement)
    except ChatRuntimeError as error:
        store.update(row['id'], {'status': 'failed', 'error': str(error)})
        raise


def _alive(row: ChatRecord) -> bool:
    try:
        return _tmux(row['socket'], 'display-message', '-p', '-t', row['pane'], '#{pane_id}') == row['pane']
    except ChatRuntimeError:
        return False


def focus_chat(chat_id: str) -> ChatRecord:
    row = ChatStore().get(chat_id)
    if not _alive(row):
        raise ChatRuntimeError('Chat pane is closed; resume the saved session')
    if row['placement'] == 'popup':
        command = shlex.join(['env', '-u', 'TMUX', 'tmux', '-S', row['socket'], 'attach-session', '-t', row['holding_session']])
        # run-shell queues the popup outside the caller's own popup lifetime.
        _tmux(row['socket'], 'run-shell', '-b', 'sleep 0.15; ' + shlex.join(['tmux', '-S', row['socket'], 'display-popup', '-E', '-t', row['host_main'], '-w', '90%', '-h', '90%', command]))
    else:
        _tmux(row['socket'], 'select-window', '-t', row['pane'])
        _tmux(row['socket'], 'select-pane', '-t', row['pane'])
    return row


def move_chat(chat_id: str, placement: str) -> ChatRecord:
    store = ChatStore()
    with store.lock(chat_id):
        row = store.get(chat_id)
        if not _alive(row):
            raise ChatRuntimeError('Chat pane is no longer running')
        socket, pane = row['socket'], row['pane']
        match placement:
            case 'popup':
                session = _tmux(socket, 'display-message', '-p', '-t', pane, '#{session_name}')
                if session != row['holding_session']:
                    placeholder = _tmux(socket, 'new-session', '-d', '-s', row['holding_session'], '-P', '-F', '#{pane_id}', 'sleep 86400')
                    _tmux(socket, 'set-option', '-t', row['holding_session'], 'detach-on-destroy', 'on')
                    _tmux(socket, 'join-pane', '-d', '-s', pane, '-t', placeholder)
                    _tmux(socket, 'kill-pane', '-t', placeholder)
            case 'left' | 'below':
                if pane == row['host_main']:
                    raise ChatRuntimeError('The host main chat cannot be docked into itself')
                flags = ['-h', '-b'] if placement == 'left' else ['-v']
                _tmux(socket, 'join-pane', '-s', pane, '-t', row['host_main'], *flags)
            case 'window':
                _tmux(socket, 'break-pane', '-d', '-s', pane, '-t', row['host_session'] + ':')
            case _:
                raise ChatRuntimeError(f'Unknown placement: {placement}')
        row = store.update(chat_id, {'placement': placement})
    return focus_chat(chat_id)


def close_chat(chat_id: str) -> ChatRecord:
    store = ChatStore()
    with store.lock(chat_id):
        row = store.get(chat_id)
        if row['pane'] == row['host_main']:
            raise ChatRuntimeError('Close the host main chat through OpenCode')
        if _alive(row):
            _tmux(row['socket'], 'kill-pane', '-t', row['pane'])
        return store.update(chat_id, {'status': 'closed'})


def rename_chat(chat_id: str, title: str) -> ChatRecord:
    if not title.strip():
        raise ChatRuntimeError('A chat title cannot be empty')
    return ChatStore().update(chat_id, {'title': title.strip()})


def adopt_main(project: str, session_id: str, pane_id: str, title: str = 'Hauptchat') -> ChatRecord:
    existing = next((row for row in list_chats(project) if row['pane'] == pane_id), None)
    if existing:
        return existing
    row = _record(LaunchOptions(project=project, resume_id=session_id, placement='window'))
    row.update(pane=pane_id, host_main=pane_id, status='running', title=title)
    _tmux(row['socket'], 'set-option', '-p', '-t', pane_id, '@ananta_chat', row['id'])
    return ChatStore().save(row)
