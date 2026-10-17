#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# Run: python3 cockpit/menus.py MENU PROJECT [CHAT_ID]
"""Small native tmux dropdowns backed by the shared action catalog."""
from pathlib import Path
import shlex
import subprocess
import sys

from catalog import ACTIONS, MENUS, actions_for, menu_shortcut, shortcut, submenus_for


def menu_command(menu: str, project: str, chat_id: str = '',
                 root: str | Path | None = None) -> str:
    MENUS[menu]
    directory = Path(root) if root is not None else Path(__file__).resolve().parent
    return shlex.join(['python3', str(directory / 'menus.py'), menu, project, chat_id])


def dispatch_command(action: str, project: str, chat_id: str = '',
                     root: str | Path | None = None) -> str:
    ACTIONS[action]
    directory = Path(root) if root is not None else Path(__file__).resolve().parent
    return shlex.join(['python3', str(directory / 'app.py'), 'dispatch', action,
                       project, chat_id])


def literal(text: str) -> str:
    """Escape tmux formats in externally supplied display text and shell strings."""
    return text.replace('#', '##').replace('\n', ' ').replace('\r', ' ')


def _run_shell(command: str) -> str:
    # display-menu and run-shell each expand formats once.
    return 'run-shell -b ' + shlex.quote(command.replace('#', '####'))


def build_menu(menu: str, project: str, chat_id: str = '', prefix: str = 'C-b',
               root: str | Path | None = None) -> list[str]:
    """Build argv without a shell; tmux supplies arrow, Enter and Escape handling."""
    selected = MENUS[menu]
    title = selected.label
    if chat_id:
        title += ' · ' + chat_id[:32]
    args = ['tmux', 'display-menu', '-T', literal(title), '-x', 'M', '-y', 'S']
    for child in submenus_for(menu):
        args.extend([f'{child.label} >  {menu_shortcut(child.id, prefix)}', child.key,
                     _run_shell(menu_command(child.id, project, chat_id, root))])
    for action in actions_for(menu):
        args.extend([f'{action.label}  {shortcut(action.id, prefix)}', action.key,
                     _run_shell(dispatch_command(action.id, project, chat_id, root))])
    if selected.parent:
        args.extend(['', 'Zurueck', 'Left',
                     _run_shell(menu_command(selected.parent, project, chat_id, root))])
    return args


def show_menu(menu: str, project: str, chat_id: str = '') -> int:
    """Query the active session prefix and open its native menu."""
    prefix = subprocess.run(['tmux', 'show-options', '-v', 'prefix'],
                            capture_output=True, text=True, check=True).stdout.strip()
    return subprocess.run(build_menu(menu, project, chat_id, prefix), check=False).returncode


def main() -> int:
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in MENUS:
        print('Aufruf: menus.py MENU PROJEKT [CHAT_ID]', file=sys.stderr)
        return 2
    try:
        return show_menu(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else '')
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'Menue konnte nicht geoeffnet werden: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
