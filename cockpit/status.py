#!/usr/bin/env python3
"""Live status tabs and safe session-scoped status/key dispatch."""
import os
from pathlib import Path
import subprocess
import sys

from catalog import MENUS
from chat_runtime import list_chats
from chat_store import ChatStoreError


def clean_title(value: str) -> str:
    return ''.join(character for character in value if character.isprintable()).replace('#', '##')


def render(project: str, active_pane: str = '') -> str:
    """Render trusted range identifiers and literal user-provided chat titles."""
    chunks = ['#[fg=colour109] Chats #[default]']
    for index, chat in enumerate(row for row in list_chats(project) if row['status'] != 'closed'):
        chat_id = chat['id']
        if not chat_id.replace('-', '').replace('_', '').isalnum():
            continue
        color = 'colour81,bold' if chat['pane'] == active_pane else 'colour252'
        title = clean_title(chat['title'])[:26]
        kind = 'S' if chat['kind'] == 'side' else 'M'
        index_label = str(index + 1) if index < 9 else '·'
        chunks.append(f'#[range=user|chat-{chat_id}]#[fg={color}] {index_label}:{kind} {title} #[default]#[norange]')
    chunks.append('#[range=user|menu-chat]#[fg=colour109] + #[default]#[norange]')
    return ''.join(chunks)


def session_option(session: str, name: str) -> str:
    return subprocess.check_output(['tmux', 'show-options', '-v', '-t', session, name], text=True).strip()


def dispatch(kind: str, value: str, session: str, button: str = 'left') -> int:
    """Resolve shell-sensitive values from options, never interpolate them into shell code."""
    project = session_option(session, '@ananta_project')
    root = Path(session_option(session, '@ananta_root'))
    command = ['python3', str(root / 'app.py'), 'dispatch', value, project]
    if kind == 'menu':
        if value not in MENUS:
            return 2
        command = ['python3', str(root / 'menus.py'), value, project]
    if kind == 'click':
        if value.startswith('menu-'):
            return dispatch('menu', value[5:], session)
        if not value.startswith('chat-'):
            return 0
        chat_id = value[5:]
        command = (['python3', str(root / 'menus.py'), 'chat', project, chat_id]
                   if button == 'right' else
                   ['python3', str(root / 'app.py'), 'dispatch', 'chat-focus', project, chat_id])
    return subprocess.run(command, check=False).returncode


def main() -> int:
    args = sys.argv[1:]
    try:
        if args and args[0] == 'render-session':
            print(render(session_option(args[1], '@ananta_project'), args[2] if len(args) > 2 else ''))
            return 0
        if args and args[0] == 'render':
            print(render(args[1], args[2] if len(args) > 2 else os.environ.get('TMUX_PANE', '')))
            return 0
        if len(args) >= 3:
            return dispatch(args[0], args[1], args[2], args[3] if len(args) > 3 else 'left')
        return 2
    except (OSError, subprocess.CalledProcessError, ChatStoreError) as error:
        print(f'Ananta: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
