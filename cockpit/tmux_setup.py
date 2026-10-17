#!/usr/bin/env python3
"""Ananta Cockpit – tmux-Layout und Statusleiste.

Robustheiten:
- start ist idempotent (vorhandenes CONTROL-Pane wird erkannt, kein zweites erzeugt)
- Pane wird nach dem Anlegen geprueft; Fehler fuehren zu sauberem Abbruch statt
  'can't find pane: %1'
- CONTROL-Pane wird per Pane-User-Option @ananta_cockpit markiert (zuverlaessiger
  als der Pane-Titel); Titel wird zusaetzlich gesetzt (best effort)
- Mausbindung wird vor dem Ueberschreiben gesichert und bei stop wiederhergestellt
- Alle tmux-Aufrufe mit Fehlerbehandlung
"""
import json
import re
import shlex
import tempfile
import subprocess
import sys
from pathlib import Path

from catalog import submenus_for

MARKER = '@ananta_cockpit'


class TmuxError(RuntimeError):
    pass


def tm(*args, check=True):
    try:
        out = subprocess.check_output(['tmux', *args], text=True, stderr=subprocess.STDOUT)
        return out.strip()
    except subprocess.CalledProcessError as e:
        if check:
            raise TmuxError(f"tmux {' '.join(args)}: {e.output.strip()}") from e
        return None
    except FileNotFoundError:
        raise TmuxError('tmux nicht gefunden')


def run(*args, check=True):
    return tm(*args, check=check)


def pane_exists(pane_id):
    if not pane_id:
        return False
    out = tm('list-panes', '-a', '-F', '#{pane_id}', check=False)
    return bool(out) and pane_id in out.splitlines()


def find_control_pane():
    """Liefert pane_id des CONTROL-Panels der aktuellen Session (oder None)."""
    out = tm('list-panes', '-F', '#{pane_id}:::#{@ananta_cockpit}:::#{pane_title}', check=False)
    if not out:
        return None
    for line in out.splitlines():
        parts = line.split(':::')
        if len(parts) >= 2 and parts[1] == '1':
            return parts[0]
        # Fallback: Titel aus frueheren Versionen
        if len(parts) >= 3 and parts[2].startswith('ANANTA CONTROL'):
            return parts[0]
    return None


def bind_exists():
    out = tm('list-keys', '-T', 'root', 'MouseDown1Status', check=False)
    return bool(out and out.strip())


BINDINGS = (('prefix', 'g'), ('root', 'MouseDown1Status'), ('root', 'MouseDown3Status'))


def source_commands(commands: str) -> None:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tmux') as config:
        config.write(commands)
        config.flush()
        run('source-file', config.name)


def install_bindings(root: str) -> None:
    saved = tm('show-options', '-gqv', '@ananta_saved_bindings', check=False)
    if saved:
        return
    bindings = {f'{table}:{key}': tm('list-keys', '-T', table, key, check=False) or ''
                for table, key in BINDINGS}
    bindings['ananta'] = tm('list-keys', '-T', 'ananta', check=False) or ''
    run('set-option', '-g', '@ananta_saved_bindings', json.dumps(bindings))
    script = shlex.quote(str(Path(root) / 'status.py'))
    for table, key in BINDINGS:
        previous = bindings[f'{table}:{key}']
        fallback = re.sub(r'^bind-key\s+(?:-r\s+)?-T\s+\S+\s+\S+\s+', '', previous) if previous else ''
        action = 'switch-client -T ananta'
        if table == 'root':
            button = 'right' if key == 'MouseDown3Status' else 'left'
            command = f"python3 {script} click '#{{mouse_status_range}}' '#{{session_id}}' {button}"
            action = 'run-shell -b ' + shlex.quote(command)
        run('bind-key', '-T', table, key, 'if-shell', '-F', '#{@ananta_root}', action, fallback)
    run('unbind-key', '-a', '-T', 'ananta', check=False)
    for menu in submenus_for('root'):
        run('bind-key', '-T', 'ananta', menu.key, 'run-shell', '-b',
            f"python3 {script} menu {menu.id} '#{{session_id}}'")
    run('bind-key', '-T', 'ananta', 'Escape', 'switch-client', '-T', 'root')
    run('bind-key', '-T', 'ananta', 'g', 'run-shell', '-b',
        f"python3 {script} menu root '#{{session_id}}'")
    for number in range(1, 10):
        run('bind-key', '-T', 'ananta', str(number), 'run-shell', '-b',
            f"python3 {script} action tab-{number} '#{{session_id}}'")


def restore_bindings() -> None:
    saved = tm('show-options', '-gqv', '@ananta_saved_bindings', check=False)
    if not saved:
        return
    bindings = json.loads(saved)
    for table, key in BINDINGS:
        run('unbind-key', '-T', table, key, check=False)
        if bindings[f'{table}:{key}']:
            source_commands(bindings[f'{table}:{key}'] + '\n')
    run('unbind-key', '-a', '-T', 'ananta', check=False)
    if bindings['ananta']:
        source_commands(bindings['ananta'] + '\n')
    run('set-option', '-gu', '@ananta_saved_bindings')


def start(root, project, state):
    sess = tm('display-message', '-p', '#{session_id}')
    main = tm('display-message', '-p', '#{pane_id}')
    markers = tm('list-panes', '-F', '#{@ananta_main}', check=False) or ''
    if '1' not in markers.splitlines() and main != find_control_pane():
        run('set-option', '-p', '-t', main, '@ananta_main', '1')
    session_key = sess.replace('$', '')
    saved = state / f'session-{session_key}.json'

    options = ('status', 'status-position', 'status-left', 'status-left-length',
               'status-right', 'status-right-length', 'mouse', 'status-style',
               'status-format', 'status-interval', '@ananta_root', '@ananta_project')
    if not saved.exists():
        local = tm('show-options', '-t', sess, check=False) or ''
        settings = {'_local_lines': [line for line in local.splitlines()
                     if line.split(' ', 1)[0].split('[', 1)[0] in options]}
        state.mkdir(parents=True, exist_ok=True)
        saved.write_text(json.dumps(settings, indent=2))
    run('set-option', '-t', sess, '@ananta_root', str(root))
    run('set-option', '-t', sess, '@ananta_project', project)
    run('set-option', '-t', sess, 'status', '2')
    run('set-option', '-t', sess, 'status-position', 'top')
    run('set-option', '-t', sess, 'status-interval', '1')
    run('set-option', '-t', sess, 'mouse', 'on')
    run('set-option', '-t', sess, 'status-style', 'bg=colour235,fg=colour252')
    prefix = tm('show-options', '-v', '-t', sess, 'prefix') or 'C-b'
    chunks = ['#[fg=colour81,bold] ANANTA #[default]']
    for menu in submenus_for('root'):
        chunks.append(f'#[range=user|menu-{menu.id}]#[fg=colour229] {menu.label} ({menu.key}) #[default]#[norange]')
    chunks.append(f'#[align=right]#[fg=colour109] {prefix} g  #[default]')
    run('set-option', '-t', sess, 'status-format[0]', ''.join(chunks))
    status_script = shlex.quote(str(Path(root) / 'status.py'))
    run('set-option', '-t', sess, 'status-format[1]',
        f"#(python3 {status_script} render-session '#{{session_id}}' '#{{pane_id}}')")
    install_bindings(root)

    # Bereits vorhandenes CONTROL-Panel? Dann nur Statusleiste erneuert.
    existing = find_control_pane()
    if existing and pane_exists(existing):
        run('select-pane', '-t', existing, '-T', 'ANANTA CONTROL', check=False)
        print('Cockpit laeuft bereits – Statusleiste erneuert.')
        return

    pane = tm('split-window', '-h', '-l', '36', '-c', project, '-P', '-F', '#{pane_id}',
              shlex.join(['bash', str(Path(root) / 'cockpit'), 'sidebar', project]))
    if not pane_exists(pane):
        raise TmuxError(f'CONTROL-Pane {pane!r} wurde nicht angelegt oder ist sofort beendet. '
                        f'Pruefe: bash "{root}/cockpit" sidebar "{project}"')
    try:
        # Marker setzen (identifiziert das Panel zuverlaessig, auch ohne Titel).
        run('set-option', '-p', '-t', pane, MARKER, '1')
    except TmuxError:
        raise TmuxError(f'CONTROL-Pane {pane} wurde sofort beendet (Sidebar-Prozess abgestuerzt). '
                        f'Pruefe: bash "{root}/cockpit" sidebar "{project}"')
    run('select-pane', '-t', pane, '-T', 'ANANTA CONTROL', check=False)
    run('select-pane', '-L')
    print(f'Cockpit gestartet. Menues per Maus oder {prefix} g, danach p/c/k/a/m/w/h. '
          f'{prefix} g 1–9 wechselt den Chat.')


def stop(root, project, state):
    sess = tm('display-message', '-p', '#{session_id}')
    session_key = sess.replace('$', '')
    saved = state / f'session-{session_key}.json'

    removed = 0
    for _ in range(4):  # nie mehr als ein paar Runden
        pane = find_control_pane()
        if not pane or not pane_exists(pane):
            break
        run('kill-pane', '-t', pane, check=False)
        removed += 1

    if saved.exists():
        settings = json.loads(saved.read_text())
        for option in ('status', 'status-position', 'status-left', 'status-left-length',
                       'status-right', 'status-right-length', 'mouse', 'status-style',
                       'status-format', 'status-interval', '@ananta_root', '@ananta_project'):
            run('set-option', '-u', '-t', sess, option, check=False)
        for line in settings.get('_local_lines', []):
            source_commands(f'set-option -t {shlex.quote(sess)} {line}\n')
        saved.unlink()
    remaining = tm('list-sessions', '-F', '#{@ananta_root}', check=False) or ''
    if not remaining.strip():
        restore_bindings()
    print(f'Cockpit gestoppt ({removed} Panel(s) entfernt). '
          'Optionen wiederhergestellt.')


def main():
    if len(sys.argv) < 5:
        print('Aufruf: tmux_setup.py start|stop ROOT PROJEKT STATE', file=sys.stderr)
        sys.exit(2)
    op, root, project, state = sys.argv[1:5]
    project = str(Path(project).expanduser().resolve())
    state = Path(state)
    try:
        if op == 'start':
            start(root, project, state)
        elif op == 'stop':
            stop(root, project, state)
        else:
            print(f'Unbekannte Operation: {op}', file=sys.stderr)
            sys.exit(2)
    except TmuxError as e:
        print(f'Fehler: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
