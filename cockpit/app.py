import os
import shlex
import subprocess
import sys
from pathlib import Path

from catalog import ACTIONS, shortcut
from chat_runtime import ChatRuntimeError, current_chat, focus_chat, host_context, list_chats
from chat_store import ChatStoreError
from commands import choose

ROOT = Path(__file__).resolve().parent
DIRECT = ('view-', 'tab-', 'chat-focus', 'cockpit-stop')


def tm(*args):
    return subprocess.run(['tmux', *args], text=True, capture_output=True, check=True).stdout.strip()


def selected(project, chat_id=''):
    rows = list_chats(project)
    if chat_id:
        return next((row for row in rows if row['id'] == chat_id), None)
    current = current_chat()
    if current:
        return current
    pane = tm('display-message', '-p', '#{pane_id}')
    return next((row for row in rows if row['pane'] == pane), None)


def view(action, project, chat):
    from chat_actions import pick_chat
    from chat_runtime import move_chat
    context = host_context()
    target = chat['pane'] if chat else context['host_main']
    name = action.removeprefix('view-')
    if name in ('left', 'below', 'window', 'popup'):
        chat = chat or pick_chat(project, side=True)
        if chat:
            move_chat(chat['id'], name)
    elif name in ('next', 'prev'):
        rows = [row for row in list_chats(project) if row['status'] != 'closed']
        if rows:
            index = next((i for i, row in enumerate(rows) if chat and row['id'] == chat['id']), 0)
            focus_chat(rows[(index + (1 if name == 'next' else -1)) % len(rows)]['id'])
    elif name in ('sidebar', 'sidebar-focus'):
        panes = tm('list-panes', '-t', context['host_session'], '-F', '#{pane_id}|#{@ananta_cockpit}').splitlines()
        sidebar = next((p.split('|')[0] for p in panes if p.endswith('|1')), '')
        if sidebar:
            tm('select-pane' if name == 'sidebar-focus' else 'kill-pane', '-t', sidebar)
        else:
            from tmux_setup import start
            start(str(ROOT), project, Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'ananta-cockpit')
    elif name.startswith('resize-'):
        tm('resize-pane', '-t', target, '-' + {'left':'L','right':'R','up':'U','down':'D'}[name[7:]], '5')
    else:
        commands = {'zoom':['resize-pane','-Z','-t',target], 'copy-mode':['copy-mode','-t',target],
                    'pane-next':['select-pane','-t',target,'-.+'], 'detach':['detach-client'],
                    'window-next':['next-window'], 'window-prev':['previous-window']}
        tm(*commands[name])


def execute(action, project, chat_id=''):
    os.chdir(project)
    chat = selected(project, chat_id)
    if action == 'chat-focus':
        if chat:
            focus_chat(chat['id'])
    elif action.startswith('tab-'):
        rows = [r for r in list_chats(project) if r['status'] != 'closed']
        index = int(action[4:]) - 1
        if index < len(rows):
            focus_chat(rows[index]['id'])
    elif action.startswith('view-'):
        view(action, project, chat)
    elif action.startswith(('chat-', 'model-', 'project-')):
        from chat_actions import execute as chat_execute
        chat_execute(action, project, chat)
    elif action.startswith('context-'):
        if action in ('context-config', 'context-snapshots'):
            from tool_actions import execute as tool_execute
            tool_execute(action, project)
        else:
            from context_sync import execute as sync_execute
            sync_execute(action, project, chat)
    elif action == 'help':
        prefix = tm('show-options', '-v', 'prefix')
        for item in ACTIONS.values():
            print(f'{item.label:36} {shortcut(item.id, prefix)}')
        print('\nListen: Pfeile, Enter, Esc, Tippen = Filter, F2/Rechtsklick = ID kopieren.')
        print('Windows Terminal: Shift + Maus markieren; Ctrl+Shift+C / Ctrl+Shift+V.')
        print('Popup ausblenden: Prefix+d im inneren tmux. Chat bleibt geoeffnet.')
    elif action == 'clipboard-copy':
        tm('copy-mode', '-t', chat['pane'] if chat else host_context()['host_main'])
        print('Im Copy-Modus mit Maus markieren; Enter kopiert in den tmux-Puffer.')
    elif action == 'clipboard-paste':
        tm('paste-buffer', '-t', chat['pane'] if chat else host_context()['host_main'])
    elif action == 'cockpit-stop':
        subprocess.run(['bash', str(ROOT/'cockpit'), 'stop', project], check=True)
    else:
        from tool_actions import execute as tool_execute
        if not tool_execute(action, project):
            raise ValueError(f'Unbekannte Aktion: {action}')


def main():
    if len(sys.argv) < 4:
        return 2
    mode, action, project = sys.argv[1:4]
    chat_id = sys.argv[4] if len(sys.argv) > 4 else ''
    if action not in ACTIONS and not action.startswith('tab-') and action != 'chat-focus':
        print('Unbekannte Aktion:', action, file=sys.stderr)
        return 2
    project = str(Path(project).expanduser().resolve())
    if mode == 'dispatch' and not sys.stdin.isatty() and not action.startswith(DIRECT):
        command = shlex.join([sys.executable, str(ROOT/'app.py'), 'interactive', action, project, chat_id])
        return subprocess.run(['tmux','display-popup','-E','-w','90%','-h','85%','-d',project,command], check=False).returncode
    try:
        execute(action, project, chat_id)
        if mode == 'interactive' and not action.startswith(('chat-', 'project-')):
            choose('\nEnter zum Schliessen ... ')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, ChatRuntimeError, ChatStoreError) as error:
        print('Fehler:', error, file=sys.stderr)
        if sys.stdin.isatty():
            choose('\nEnter zum Schliessen ... ')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
