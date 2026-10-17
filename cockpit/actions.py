#!/usr/bin/env python3
"""Ananta Cockpit – Aktions-Popups. Alle Aktionen sind read-only oder explizit bestaetigt."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

action, project, root = sys.argv[1:4]
project = str(Path(project).expanduser().resolve())
SESSION_RE = re.compile(r'^ses_[A-Za-z0-9_-]+$')


def pause(msg='\nEnter zum Schliessen ...'):
    try:
        input(msg)
    except EOFError:
        pass


def run(argv, cwd=None):
    try:
        return subprocess.run(argv, cwd=cwd or project, check=False, text=True,
                              capture_output=False)
    except FileNotFoundError:
        print('Befehl nicht vorhanden:', argv[0])
        return None


def run_capture(argv, cwd=None):
    try:
        p = subprocess.run(argv, cwd=cwd or project, check=False, text=True,
                           capture_output=True)
        return (p.stdout or '') + (p.stderr or '')
    except FileNotFoundError:
        return ''


def choose(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ''


def confirm(prompt, expected='JA'):
    val = choose(f'{prompt} [ja/NEIN]: ').strip().lower()
    return val in ('ja', 'j', expected.lower())


def list_sessions():
    """Liefert Liste von Session-IDs aus `opencode session list`."""
    out = run_capture(['opencode', 'session', 'list'])
    ids = re.findall(r'ses_[A-Za-z0-9_-]+', out)
    return list(dict.fromkeys(ids)), out


def valid_session(sid, known):
    return bool(SESSION_RE.fullmatch(sid or '')) and (not known or sid in known)


print(f'\n  ANANTA COCKPIT  /  {action.upper()}\n  Projekt: {project}\n')

if action == 'side':
    state_dir = Path.home() / '.local/state/ananta-cockpit'
    side_log = state_dir / 'side-chats.json'
    recorded = []
    if side_log.exists():
        try:
            recorded = json.loads(side_log.read_text())
        except Exception:
            recorded = []

    print('Side-Chat: Fork einer Hauptsitzung in einem Popup.')
    print('  o = Side-Chat oeffnen   c = temporaere Side-Chats aufraeumen   Enter = Abbrechen')
    if recorded:
        print(f'\nErfasste Side-Chats ({len(recorded)}):')
        for i, e in enumerate(recorded, 1):
            print(f"  {i}. {e.get('id')}  (von {e.get('parent','?')}, {e.get('created','')[:16]})")
    mode = choose('\nAuswahl [o/c/Enter]: ').lower()
    if mode == 'c':
        if not recorded:
            print('Keine erfassten Side-Chats vorhanden.')
        else:
            ids, out = list_sessions()
            print()
            targets = choose('Aufraeumen: Nummern (z.B. 1,2), "all" oder Enter=Abbrechen: ').lower()
            selected = []
            if targets == 'all':
                selected = [e for e in recorded if e.get('id') in ids]
            else:
                for tok in targets.replace(',', ' ').split():
                    if tok.isdigit() and 1 <= int(tok) <= len(recorded):
                        e = recorded[int(tok) - 1]
                        if e.get('id') in ids:
                            selected.append(e)
            if not selected:
                print('Nichts ausgewaehlt (nur existierende Sitzungen sind loeschbar).')
            else:
                print(f'\nFolgende Side-Chats werden GELÖSCHT: {", ".join(e["id"] for e in selected)}')
                if confirm('Endgueltig loeschen?'):
                    for e in selected:
                        r = run_capture(['opencode', 'session', 'delete', e['id']])
                        print(f"  {e['id']}: {r.strip() or 'geloescht'}")
                    remaining = [e for e in recorded if e not in selected]
                    side_log.write_text(json.dumps(remaining, indent=2) + '\n')
                else:
                    print('Nichts geloescht.')
    elif mode == 'o' or mode == '':
        if mode == '':
            print('Abgebrochen.')
        else:
            ids, out = list_sessions()
            print(out if out.strip() else '(keine Sitzungen gefunden – ist OpenCode gestartet?)')
            if not ids:
                print('Keine gueltigen Sitzungs-IDs verfuegbar.')
            else:
                session = choose('\nHauptsitzungs-ID: ')
                if not session:
                    print('Abgebrochen.')
                elif not valid_session(session, ids):
                    print(f'Ungueltige oder unbekannte Session-ID: {session}')
                else:
                    model = choose('Modell [xiaomi-token-plan-ams/mimo-v2.6-flash]: ') or \
                        'xiaomi-token-plan-ams/mimo-v2.6-flash'
                    if shutil.which('oc-side'):
                        print(f'Starte Side-Chat fuer {session} mit {model} ...')
                        run(['oc-side', '--session', session, '--dir', project, '--model', model])
                    else:
                        print('oc-side nicht installiert. Alternative im OpenCode-TUI: /fork')
                        print('CLI-Variante: opencode --session', session, '--fork')
    else:
        print('Abgebrochen.')

elif action == 'sessions':
    ids, out = list_sessions()
    print(out if out.strip() else '(keine Sitzungen gefunden)')
    if ids:
        print('\nGefundene IDs:', ', '.join(ids))

elif action == 'models':
    print('Verfuegbare Modelle (laeuft keine Aenderung der laufenden Sitzung):\n')
    run(['opencode', 'models'])

elif action == 'plans':
    if shutil.which('slim-plan'):
        run(['slim-plan', 'brief'])
    else:
        p = Path(project) / '.opencode/slim-context'
        print('Planverzeichnis:', p)
        if p.exists():
            for x in sorted(p.rglob('*.json')):
                print(' ', x.relative_to(p))
        else:
            print('Keine Plan-Dateien gefunden')

elif action == 'logs':
    candidates = [Path('/tmp/opencode-slim-router.log'),
                  Path.home() / '.local/state/opencode-slim-router.log',
                  Path('/tmp/opencode-slim-context.log')]
    shown = False
    for p in candidates:
        if p.exists():
            shown = True
            print('Log:', p)
            lines = p.read_text(errors='replace').splitlines()
            print('\n'.join(lines[-55:]))
            print()
    if not shown:
        print('Keine Logdateien vorhanden.')

elif action == 'router':
    health_file = Path(project) / '.opencode/slim-context/router/model-health.json'
    cfg_file = Path.home() / '.config/opencode/slim-router.json'
    print('Router-Konfiguration:', cfg_file)
    if cfg_file.exists():
        try:
            d = json.loads(cfg_file.read_text())
            print('  enabled:', d.get('enabled'))
            print('  failback_enabled:', d.get('failback_enabled'))
            print('  max_attempts:', d.get('max_attempts'))
            print('  fallback_models:')
            for m in d.get('fallback_models', []):
                print('   -', m)
        except Exception as e:
            print('  Konfiguration nicht lesbar:', e)
    else:
        print('  nicht vorhanden')
    print('\nModell-Gesundheit (Cooldowns):', health_file)
    if health_file.exists():
        try:
            health = json.loads(health_file.read_text())
            if not health:
                print('  keine Eintraege')
            import datetime
            for model, h in health.items():
                until = h.get('blockedUntil', 0)
                status = 'BLOCKIERT' if until > int(datetime.datetime.now().timestamp() * 1000) else 'ok'
                ts = datetime.datetime.fromtimestamp(until / 1000).isoformat() if until else '-'
                print(f'  {model}: {status} bis {ts} failures={h.get("failures", 0)}')
                reason = (h.get('reason') or '')[:120]
                if reason:
                    print(f'    Grund: {reason}')
        except Exception as e:
            print('  nicht lesbar:', e)
    else:
        print('  keine Datei – noch keine Fehler aufgezeichnet.')

elif action == 'sync':
    ids, out = list_sessions()
    print(out if out.strip() else '(keine Sitzungen gefunden)')
    if not shutil.which('oc-side-sync'):
        print('oc-side-sync ist nicht installiert. Bitte install.sh erneut ausfuehren.')
    else:
        main = choose('Hauptsitzungs-ID: ')
        side = choose('Side-Sitzungs-ID: ')
        direction = choose('Richtung [main-to-side/side-to-main]: ') or 'main-to-side'
        if not (valid_session(main, ids) and valid_session(side, ids) and main != side):
            print('Abbruch: zwei verschiedene, gueltige Sitzungs-IDs erforderlich.')
        elif direction not in ('main-to-side', 'side-to-main'):
            print('Abbruch: ungueltige Richtung.')
        else:
            print('\n--- VORSCHAU (es wurde nichts uebertragen) ---\n')
            run(['oc-side-sync', 'preview', '--main', main, '--side', side,
                 '--direction', direction])
            if confirm('\nWirklich uebernehmen?'):
                run(['oc-side-sync', 'apply', '--main', main, '--side', side,
                     '--direction', direction, '--yes'])
            else:
                print('Nicht uebernommen.')

elif action == 'help':
    print('Menueleiste oben anklicken oder im Panel 1–7 druecken.')
    print('  1 Side-Chat   2 Sessions   3 Modelle   4 Plaene')
    print('  5 Sync        6 Router     7 Logs')
    print('q beendet das Panel. Ctrl+B + Pfeile wechseln das Pane.')
else:
    print('Unbekannte Aktion:', action)

pause()
