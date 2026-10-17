import curses
import sys
import unicodedata
from dataclasses import dataclass
from collections.abc import Sequence
from clipboard import copy_text


@dataclass(frozen=True, slots=True)
class Choice:
    value: str
    label: str


def select(title: str, choices: Sequence[Choice], multiple: bool = False) -> list[str]:
    """Liefert gewaehlte Werte; Abbruch und leere Listen liefern []."""
    if not choices:
        return []
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(title)
        for index, choice in enumerate(choices, 1):
            print(f'  {index}. {choice.label}')
        try:
            answer = input('Nummer(n), durch Komma getrennt; Enter = Abbrechen: ')
        except EOFError:
            return []
        tokens = answer.replace(',', ' ').split()
        if not tokens or (not multiple and len(tokens) != 1):
            return []
        if any(not token.isdigit() or not 1 <= int(token) <= len(choices) for token in tokens):
            return []
        indices = {int(token) - 1 for token in tokens}
        return [choice.value for index, choice in enumerate(choices) if index in indices]
    try:
        return curses.wrapper(lambda screen: _select(screen, title, choices, multiple))
    except KeyboardInterrupt:
        return []


def _line(screen, row: int, text: str, attr: int = 0) -> None:
    height, width = screen.getmaxyx()
    if not 0 <= row < height or width < 3:
        return
    clean = ''.join(char if char.isprintable() else ' ' for char in text)
    cells_by_char = [(char, 0 if unicodedata.combining(char) else
                      (2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1)) for char in clean]
    shortened = sum(cells for _, cells in cells_by_char) > width - 2
    limit = width - 5 if shortened and width >= 5 else width - 2
    clipped = ''
    used = 0
    for char, cells in cells_by_char:
        if used + cells > limit:
            break
        clipped += char
        used += cells
    if shortened and width >= 5:
        clipped += '...'
    try:
        screen.addstr(row, 1, clipped, attr)
    except curses.error:
        pass


def _select(screen, title: str, choices: Sequence[Choice], multiple: bool) -> list[str]:
    curses.curs_set(0)
    curses.set_escdelay(30)
    curses.mouseinterval(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    screen.keypad(True)
    query = ''
    cursor = 0
    top = 0
    selected: set[str] = set()
    status = ''
    while True:
        visible = [choice for choice in choices if query.casefold() in choice.label.casefold()]
        cursor = max(0, min(cursor, len(visible) - 1))
        height, width = screen.getmaxyx()
        if height < 8 or width < 24:
            screen.erase()
            _line(screen, 0, 'Fenster vergroessern; Esc: abbrechen')
            screen.refresh()
            if screen.get_wch() in ('\x1b', '\x03'):
                return []
            continue
        page = max(1, height - 6)
        top = max(0, min(top, cursor))
        if cursor >= top + page:
            top = cursor - page + 1
        screen.erase()
        _line(screen, 0, title, curses.A_BOLD)
        _line(screen, 1, 'Pfeile: navigieren | Enter: uebernehmen | Esc: abbrechen' if width >= 60
              else 'Enter: Wahl | Esc: Ende')
        _line(screen, 2, f'Suche: {query or "(einfach tippen)"}')
        _line(screen, 3, status)
        for index in range(top, min(len(visible), top + page)):
            choice = visible[index]
            marker = ('[x] ' if choice.value in selected else '[ ] ') if multiple else '  '
            _line(screen, 4 + index - top, marker + choice.label,
                  curses.A_REVERSE if index == cursor else 0)
        if not visible:
            _line(screen, 4, 'Keine Treffer. Suche mit Backspace loeschen oder Esc zum Abbrechen.')
        _line(screen, height - 2,
              f'{cursor + 1 if visible else 0}/{len(visible)} Treffer | {len(selected)} markiert' if multiple
              else f'{cursor + 1 if visible else 0}/{len(visible)} Treffer')
        hint = ('Space/Klick: markieren | Rechtsklick/F2: kopieren' if multiple
                else 'Klick: auswaehlen | Rechtsklick/F2: kopieren | Rad: scrollen')
        if width < 60:
            hint = 'Space/Klick: markieren | F2: Kopie' if multiple else 'Klick: Wahl | F2: Kopie'
        _line(screen, height - 1, hint)
        screen.refresh()
        key = screen.get_wch()
        if key in ('\x1b', '\x03'):
            return []
        if key in ('\n', '\r', curses.KEY_ENTER):
            if multiple:
                return [choice.value for choice in choices if choice.value in selected]
            if visible:
                return [visible[cursor].value]
        elif key in (curses.KEY_DOWN, curses.KEY_UP):
            cursor += 1 if key == curses.KEY_DOWN else -1
        elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
            cursor += page if key == curses.KEY_NPAGE else -page
        elif key in (curses.KEY_HOME, curses.KEY_END):
            cursor = 0 if key == curses.KEY_HOME else len(visible) - 1
        elif key in (curses.KEY_BACKSPACE, '\x7f', '\b'):
            query = query[:-1]
            cursor = top = 0
        elif key == curses.KEY_F2 and visible:
            value = visible[cursor].value
            status = f'Kopiert: {value}' if copy_text(value) else 'Kopieren fehlgeschlagen. Text mit Shift+Maus markieren.'
        elif key == curses.KEY_MOUSE:
            try:
                _, x, y, _, state = curses.getmouse()
            except curses.error:
                continue
            if state & curses.BUTTON4_PRESSED:
                cursor -= 3
            elif state & getattr(curses, 'BUTTON5_PRESSED', 0):
                cursor += 3
            elif (state & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED |
                           curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED)
                  and 1 <= x < width - 1 and 4 <= y < 4 + page):
                index = top + y - 4
                if index < len(visible):
                    cursor = index
                    if state & (curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED):
                        value = visible[cursor].value
                        status = f'Kopiert: {value}' if copy_text(value) else 'Kopieren fehlgeschlagen. Text mit Shift+Maus markieren.'
                        continue
                    if not multiple:
                        return [visible[cursor].value]
                    value = visible[cursor].value
                    selected.symmetric_difference_update({value})
        elif key == ' ' and multiple and visible:
            selected.symmetric_difference_update({visible[cursor].value})
        elif isinstance(key, str) and key.isprintable():
            query += key
            cursor = top = 0


def pick(title: str, choices: Sequence[Choice]) -> str | None:
    selected = select(title, choices)
    return selected[0] if selected else None
