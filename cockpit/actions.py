#!/usr/bin/env python3
"""Ananta Cockpit – Aktions-Popups. Alle Aktionen sind read-only oder explizit bestaetigt."""
import json
import os
import re
import shutil
import sys
from pathlib import Path
from selection import Choice, pick
from commands import confirm, list_sessions, pick_model, pick_session, run, run_capture, session_choices
from side_chats import manage_side_chats

action, project, root = sys.argv[1:4]
project = str(Path(project).expanduser().resolve())
os.chdir(project)


def pause(msg='\nEnter zum Schliessen ...'):
    print('\nText markieren: Shift + Maus ziehen; kopieren: Ctrl+Shift+C; einfuegen: Ctrl+Shift+V.')
    try:
        input(msg)
    except EOFError:
        pass


print(f'\n  ANANTA COCKPIT  /  {action.upper()}\n  Projekt: {project}\n')

if action == 'side':
    if manage_side_chats(project):
        sys.exit(0)

elif action == 'sessions':
    ids, out = list_sessions()
    if ids:
        session = pick('Sitzungen durchsuchen', session_choices(ids, out))
        if session:
            print('Ausgewaehlte Sitzung:', session)
    else:
        print('(keine Sitzungen gefunden)')

elif action == 'models':
    out = run_capture(['opencode', 'models'])
    models = [line.strip() for line in out.splitlines()
              if re.fullmatch(r'[^\s/]+/[^\s]+', line.strip())]
    model = pick('Modelle durchsuchen (nur Anzeige)', [Choice(model, model) for model in models])
    print(f'Modell: {model}' if model else 'Keine Auswahl. Die laufende Sitzung bleibt unveraendert.')

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

elif action == 'codecompass':
    occ = shutil.which('oc-codecompass')
    if not occ:
        print('oc-codecompass ist nicht installiert. Bitte install.sh erneut ausfuehren.')
    else:
        print('CodeCompass ueber den Ananta-Hub-MCP-Endpunkt.')
        mode = pick('CodeCompass', [Choice('s', 'Hub-Status anzeigen'),
                                    Choice('t', 'Tools anzeigen'),
                                    Choice('o', 'OpenCode mit CodeCompass starten')])
        if mode == 's':
            run([occ, 'status'])
        elif mode == 't':
            run([occ, 'tools'])
        elif mode == 'o':
            model = pick_model()
            if model:
                print('Starte OpenCode mit CodeCompass-MCP (Beenden wie ueblich)...')
                run([occ, 'run', '--model', model])
            else:
                print('Abgebrochen.')
        else:
            print('Abgebrochen.')

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
    if not shutil.which('oc-side-sync'):
        print('oc-side-sync ist nicht installiert. Bitte install.sh erneut ausfuehren.')
    else:
        main = pick_session('Hauptsitzung fuer den Kontext-Sync waehlen')
        side = pick_session('Side-Sitzung waehlen', excluded=main) if main else None
        direction = pick('Sync-Richtung', [Choice('main-to-side', 'Hauptsitzung -> Side-Sitzung'),
                                           Choice('side-to-main', 'Side-Sitzung -> Hauptsitzung')]) if side else None
        if not main or not side or not direction:
            print('Abgebrochen.')
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
    print('Menueleiste oben anklicken oder Prefix g + Menuebuchstabe (p/c/k/a/m/w/h).')
    print('Chats: Tabs in der Statusleiste oder das Chat-Baum-Panel rechts.')
    print('q beendet das Panel. Ctrl+B + Pfeile wechseln das Pane.')
else:
    print('Unbekannte Aktion:', action)

pause()
