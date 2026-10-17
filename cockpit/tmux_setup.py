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
import subprocess
import sys
from pathlib import Path

MARKER = '@ananta_cockpit'
CONTROLS = [
    ('side', 'SIDE'),
    ('sessions', 'SESSIONS'),
    ('models', 'MODELS'),
    ('plans', 'PLANS'),
    ('sync', 'SYNC'),
    ('router', 'ROUTER'),
    ('logs', 'LOGS'),
]


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


def start(root, project, state):
    sess = tm('display-message', '-p', '#{session_id}')
    session_key = sess.replace('$', '')
    saved = state / f'session-{session_key}.json'

    # Statusoptionen nur beim ersten Start sichern.
    if not saved.exists():
        settings = {}
        for k in ('status-position', 'status-left', 'status-left-length',
                  'status-right', 'status-right-length', 'mouse', 'status-style'):
            settings[k] = tm('show-options', '-gv', k, check=False) or ''
        settings['_had_mouse_binding'] = '1' if bind_exists() else '0'
        state.mkdir(parents=True, exist_ok=True)
        saved.write_text(json.dumps(settings, indent=2))

    run('set-option', '-t', sess, 'status-position', 'top')
    run('set-option', '-t', sess, 'status-left-length', '160')
    run('set-option', '-t', sess, 'status-right-length', '60')
    run('set-option', '-t', sess, 'mouse', 'on')
    run('set-option', '-t', sess, 'status-style', 'bg=colour235,fg=colour252')

    chunks = ['#[fg=colour81,bold] ANANTA #[default]']
    for i, (_action, label) in enumerate(CONTROLS):
        chunks.append(f'#[range=user|ac{i}]#[fg=colour229] {label} #[default]#[norange]')
    run('set-option', '-t', sess, 'status-left', ''.join(chunks))
    run('set-option', '-t', sess, 'status-right',
        '#[fg=colour109]#{session_name}  %H:%M ')

    # Mausbindung: skript reagiert nur auf Bereich ac0..ac6.
    script = str(Path(root) / 'status-click.sh')
    if not Path(script).is_file():
        print(f'Warnung: {script} fehlt – Menueklicks deaktiviert.')
    else:
        run('unbind-key', '-T', 'root', 'MouseDown1Status', check=False)
        run('bind-key', '-T', 'root', 'MouseDown1Status', 'run-shell', '-b',
            f'{script} "#{{mouse_status_range}}" "#{{session_id}}" "{project}" "{root}"')

    # Bereits vorhandenes CONTROL-Panel? Dann nur Statusleiste erneuert.
    existing = find_control_pane()
    if existing and pane_exists(existing):
        run('select-pane', '-t', existing, '-T', 'ANANTA CONTROL', check=False)
        print('Cockpit laeuft bereits – Statusleiste erneuert.')
        return

    pane = tm('split-window', '-h', '-l', '36', '-c', project, '-P', '-F', '#{pane_id}',
              f'bash "{root}/cockpit" sidebar "{project}"')
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
    print('Cockpit gestartet. Menue per Maus oder im Panel 1–7. '
          'Ctrl+B + Pfeile wechseln das Pane.')


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
        try:
            settings = json.loads(saved.read_text())
        except (OSError, json.JSONDecodeError):
            settings = {}
        for key, value in settings.items():
            if key.startswith('_'):
                continue
            if value != '':
                run('set-option', '-t', sess, key, value, check=False)
        if settings.get('_had_mouse_binding') != '1':
            run('unbind-key', '-T', 'root', 'MouseDown1Status', check=False)
        saved.unlink()
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
