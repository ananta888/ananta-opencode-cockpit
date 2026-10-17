#!/usr/bin/env python3
"""Ananta Cockpit – rechtes CONTROL-Panel (curses). Reihenfolge = Statusleiste."""
import curses
import subprocess
import sys
from pathlib import Path

project, root = sys.argv[1:3]
# Reihenfolge identisch zu CONTROLS in tmux_setup.py (ac0..ac6).
ENTRIES = [
    ('1', 'Side-Chat', 'side'),
    ('2', 'Sessions', 'sessions'),
    ('3', 'Modelle', 'models'),
    ('4', 'Plaene', 'plans'),
    ('5', 'Kontext-Sync', 'sync'),
    ('6', 'Router', 'router'),
    ('7', 'Logs', 'logs'),
]


def pop(action):
    cmd = ['tmux', 'display-popup', '-E', '-w', '85%', '-h', '75%', '-d', project,
           f'bash "{root}/cockpit" action {action} "{project}"']
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        pass


def app(screen):
    curses.curs_set(0)
    screen.keypad(True)
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    except curses.error:
        pass
    while True:
        screen.erase()
        h, w = screen.getmaxyx()

        def line(y, s, attr=0):
            if 0 <= y < h and w > 1:
                try:
                    screen.addnstr(y, 1, s, max(0, w - 2), attr)
                except curses.error:
                    pass

        line(0, 'ANANTA CONTROL', curses.A_BOLD)
        line(1, 'tmux / OpenCode')
        line(3, 'KLICKEN oder 1-7:')
        for idx, (key, title, _) in enumerate(ENTRIES):
            line(5 + idx, f'[{key}] {title}', curses.A_REVERSE)
        line(13, f'Projekt: {project}')
        line(15, 'Status: unabhaengig vom Router')
        line(h - 2 if h > 2 else 0, 'q = Panel schliessen')
        line(h - 1 if h > 1 else 0, 'Ctrl+B, Pfeil = Pane wechseln')
        screen.refresh()
        try:
            c = screen.getch()
        except KeyboardInterrupt:
            break
        if c in (ord('q'), 27):
            break
        chosen = None
        if c == curses.KEY_MOUSE:
            try:
                _, x, y, _, state = curses.getmouse()
                if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    for idx in range(len(ENTRIES)):
                        if y == 5 + idx:
                            chosen = ENTRIES[idx][2]
            except curses.error:
                pass
        else:
            for key, _, act in ENTRIES:
                if c == ord(key):
                    chosen = act
        if chosen:
            curses.endwin()
            try:
                pop(chosen)
            finally:
                screen.refresh()


if __name__ == '__main__':
    try:
        curses.wrapper(app)
    except KeyboardInterrupt:
        pass
