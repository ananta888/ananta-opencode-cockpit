import json
import os
import shutil
from pathlib import Path

from commands import confirm, list_sessions, pick_model, pick_session, run, run_capture, session_choices
from selection import Choice, pick, select


def manage_side_chats(project: str) -> bool:
    """True nur nach erfolgreichem Pane-Start: das aufrufende Popup darf schliessen."""
    state_dir = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'ananta-cockpit'
    side_log = state_dir / 'side-chats.json'
    recorded = []
    if side_log.exists():
        try:
            recorded = json.loads(side_log.read_text())
        except (OSError, ValueError):
            print('Side-Chat-Liste nicht lesbar. Bestehende OpenCode-Sitzungen bleiben verfuegbar.')
    mode = pick('Side-Chat', [Choice('o', 'Neuen Side-Chat oeffnen'),
                              Choice('r', 'Bestehenden Side-Chat fortsetzen'),
                              Choice('c', 'Temporaere Side-Chats aufraeumen')])
    if mode == 'c':
        ids, _ = list_sessions()
        targets = select('Side-Chats zum Loeschen markieren',
                         [Choice(e['id'], f"{e['id']} (von {e.get('parent', '?')})")
                          for e in recorded if e.get('id') in ids], multiple=True)
        selected = [e for e in recorded if e.get('id') in targets]
        if selected:
            print('Zum Loeschen ausgewaehlt:', ', '.join(e['id'] for e in selected))
            if confirm('Endgueltig loeschen?'):
                for e in selected:
                    result = run_capture(['opencode', 'session', 'delete', e['id']])
                    print(f"  {e['id']}: {result.strip() or 'geloescht'}")
                side_log.write_text(json.dumps([e for e in recorded if e not in selected], indent=2) + '\n')
        else:
            print('Keine existierenden Side-Chats ausgewaehlt.')
        return False
    if mode not in ('o', 'r'):
        print('Abgebrochen.')
        return False

    if mode == 'r':
        ids, out = list_sessions()
        known = {e.get('id') for e in recorded}
        saved = [sid for sid in ids if sid in known]
        candidates = [*saved, *(sid for sid in ids if sid not in known)]
        if not saved:
            print('Keine erfassten Side-Chats gefunden. Waehle eine bestehende OpenCode-Sitzung.')
        choices = [Choice(choice.value, choice.label + (' [Side-Chat]' if choice.value in known else ''))
                   for choice in session_choices(candidates, out)]
        session = pick('Bestehenden Side-Chat fortsetzen', choices)
        model = None
    else:
        session = pick_session('Hauptsitzung fuer den Side-Chat waehlen')
        model = pick_model() if session else None
        if not model:
            print('Abgebrochen.')
            return False
    if not session:
        print('Abgebrochen.')
        return False
    use_cc = pick('CodeCompass-MCP fuer den Side-Chat',
                  [Choice('no', 'Ohne CodeCompass starten'), Choice('yes', 'Mit CodeCompass starten')])
    if use_cc is None:
        print('Abgebrochen.')
        return False
    placement = pick('Platzierung des Side-Chats',
                     [Choice('popup', 'Popup (ueberlagert)'),
                      Choice('left', 'Links neben der Hauptsitzung'),
                      Choice('below', 'Unter der Hauptsitzung')])
    if placement is None:
        print('Abgebrochen.')
        return False
    if not shutil.which('oc-side'):
        print('oc-side nicht installiert. Bitte install.sh ausfuehren.')
        return False
    argv = ['oc-side', '--session', session, '--dir', project]
    argv += ['--inline'] if placement == 'popup' else ['--layout', placement]
    if mode == 'r':
        argv.append('--resume')
    if model:
        argv += ['--model', model]
    if use_cc == 'yes':
        argv.append('--codecompass')
    print(f'{"Setze fort" if mode == "r" else "Starte Side-Chat fuer"} {session} ...', flush=True)
    result = run(argv)
    return placement != 'popup' and result is not None and result.returncode == 0
