#!/usr/bin/env python3
"""Ananta Cockpit – rechte Seitenleiste als Chat-Baum (curses)."""
import curses
import subprocess
import sys
from pathlib import Path

from chat_runtime import list_chats

STATES = {'running': 'bereit', 'starting': 'startet', 'closed': 'geschlossen',
          'stopped': 'beendet', 'failed': 'FEHLER', 'deleted': 'geloescht'}


def app(screen, project, root):
    curses.curs_set(0)
    screen.keypad(True)
    screen.timeout(800)
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
    except curses.error:
        pass
    selected = 0
    scroll = 0
    while True:
        rows = list_chats(project)
        rows.sort(key=lambda r: (r['parent_id'] or r['session_id'], r['kind'] == 'side', r['title']))
        height, width = screen.getmaxyx()
        selected = min(selected, max(0, len(rows) - 1))
        scroll = max(0, min(scroll, selected))
        if selected >= scroll + max(1, height - 9):
            scroll = selected - max(1, height - 9) + 1
        screen.erase()

        def line(y, text, attr=0):
            if 0 <= y < height and width > 2:
                try:
                    screen.addnstr(y, 1, text, width - 2, attr)
                except curses.error:
                    pass

        line(0, 'ANANTA · CHATS', curses.A_BOLD)
        line(1, Path(project).name)
        line(3, 'Geoeffnet / gespeichert')
        for index, row in enumerate(rows[scroll:scroll + max(1, height - 9)], scroll):
            state = STATES.get(row['status'], row['status'])
            branch = '  └ ' if row['kind'] == 'side' else '▸ '
            line(4 + index - scroll, branch + row['title'] + ' · ' + state,
                 curses.A_REVERSE if index == selected else 0)
        if not rows:
            line(5, 'Noch keine verwalteten Chats')
            line(6, 'n = neuer Chat / s = Side')
        if rows:
            row = rows[selected]
            line(height - 5, (row.get('model') or 'Modell: OpenCode') + (' · MCP' if row['mcp'] else ''))
            line(height - 4, 'Sync: ' + row.get('last_sync', '—') + ' ' + row.get('last_sync_direction', ''))
            if row.get('error'):
                line(height - 3, row['error'], curses.A_BOLD)
        line(height - 2, 'Enter/Klick: oeffnen · m: Menue')
        line(height - 1, 'n: Neu · s: Side · q: ausblenden')
        screen.refresh()
        key = screen.getch()
        action = None
        chat_id = rows[selected]['id'] if rows else ''
        if key in (ord('q'), 27):
            return
        if key in (curses.KEY_DOWN, curses.KEY_UP) and rows:
            selected = (selected + (1 if key == curses.KEY_DOWN else -1)) % len(rows)
        elif key in (10, 13, curses.KEY_ENTER) and rows:
            action = 'chat-resume' if rows[selected]['status'] in ('closed', 'stopped', 'failed') else 'chat-focus'
        elif key == ord('n'):
            action = 'chat-new'
        elif key == ord('s'):
            action = 'chat-side'
        elif key == ord('m'):
            subprocess.Popen([sys.executable, str(Path(root) / 'menus.py'), 'root', project, chat_id])
        elif key == curses.KEY_MOUSE:
            try:
                _, _, y, _, state = curses.getmouse()
                index = y - 4 + scroll
                if 0 <= index < len(rows):
                    selected = index
                    chat_id = rows[index]['id']
                    if state & (curses.BUTTON3_CLICKED | curses.BUTTON3_PRESSED):
                        subprocess.Popen([sys.executable, str(Path(root) / 'menus.py'), 'chat', project, chat_id])
                    elif state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                        action = ('chat-resume' if rows[index]['status'] in ('closed', 'stopped', 'failed')
                                  else 'chat-focus')
            except curses.error:
                pass
        if action:
            subprocess.Popen([sys.executable, str(Path(root) / 'app.py'), 'dispatch', action, project, chat_id],
                             stdin=subprocess.DEVNULL)


if __name__ == '__main__':
    try:
        curses.wrapper(app, *sys.argv[1:3])
    except KeyboardInterrupt:
        pass
