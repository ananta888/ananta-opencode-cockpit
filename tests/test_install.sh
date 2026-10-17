#!/usr/bin/env bash
# Regressionstests fuer Installation und status-click.sh.
# Keine echten API-Aufrufe, kein Eingriff in die echte Installation (fakes HOME).
set -u
ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/.." && pwd)"
REAL_HOME="$HOME"
FAKE="$(mktemp -d /tmp/ac-install-test.XXXXXX)"
export HOME="$FAKE/home"
export XDG_DATA_HOME="$FAKE/home/.local/share"
export XDG_STATE_HOME="$FAKE/home/.local/state"
mkdir -p "$HOME"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   - $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL - $1"; }

echo "== install.sh (fakes HOME) =="
bash "$ROOT/install.sh" >/dev/null 2>&1 || bad 'install.sh Lauf 1'
[ -f "$XDG_DATA_HOME/ananta-cockpit/tmux_setup.py" ] && ok 'tmux_setup.py installiert' || bad 'tmux_setup.py fehlt'
[ -f "$XDG_DATA_HOME/ananta-cockpit/actions.py" ] && ok 'actions.py installiert' || bad 'actions.py fehlt'
[ -f "$XDG_DATA_HOME/ananta-cockpit/sidebar.py" ] && ok 'sidebar.py installiert' || bad 'sidebar.py fehlt'
[ -x "$XDG_DATA_HOME/ananta-cockpit/status-click.sh" ] && ok 'status-click.sh installiert+ausfuehrbar' || bad 'status-click.sh fehlt'
[ -x "$HOME/.local/bin/ananta-cockpit" ] && ok 'Wrapper ausfuehrbar' || bad 'Wrapper fehlt'
[ -x "$HOME/.local/bin/oc-side" ] && ok 'oc-side installiert' || bad 'oc-side fehlt'
[ -x "$HOME/.local/bin/oc-side-sync" ] && ok 'oc-side-sync installiert' || bad 'oc-side-sync fehlt'
[ -x "$HOME/.local/bin/slim-plan" ] && ok 'slim-plan installiert' || bad 'slim-plan fehlt'
[ -f "$HOME/.config/opencode/plugins/slim-router.ts" ] && ok 'Plugin slim-router installiert' || bad 'Plugin slim-router fehlt'
[ -f "$HOME/.config/opencode/plugins/context-manager.ts" ] && ok 'Plugin context-manager installiert' || bad 'Plugin context-manager fehlt'
[ -f "$HOME/.config/opencode/slim-router.json" ] && ok 'Config slim-router angelegt' || bad 'Config slim-router fehlt'
grep -q 'tmux_setup.py' "$XDG_DATA_HOME/ananta-cockpit/cockpit" && ok 'cockpit ist echtes Skript' || bad 'cockpit ist Self-Wrapper'
grep -q "$XDG_DATA_HOME/ananta-cockpit/cockpit" "$HOME/.local/bin/ananta-cockpit" && ok 'Wrapper zeigt auf SHARE' || bad 'Wrapper falsch'

# Idempotenz: zweiter Lauf erzeugt keine Fehler und keine Duplikate.
bash "$ROOT/install.sh" >/dev/null 2>&1 && ok 'install.sh Lauf 2 (idempotent)' || bad 'install.sh Lauf 2 fehlgeschlagen'
count=$(find "$XDG_DATA_HOME/ananta-cockpit" -maxdepth 1 -name 'tmux_setup.py' | wc -l)
[ "$count" = "1" ] && ok 'keine Duplikate' || bad "Duplikate: $count"

# Installationsverzeichnis darf nicht vom CWD abhaengen.
( cd / && "$HOME/.local/bin/ananta-cockpit" help ) >/dev/null 2>&1 && ok 'Start aus / moeglich' || bad 'Start aus / fehlgeschlagen'

# Bestehende Config darf beim 2. Lauf nicht ueberschrieben werden.
echo '{"custom": true}' > "$HOME/.config/opencode/slim-router.json"
bash "$ROOT/install.sh" >/dev/null 2>&1
grep -q '"custom": true' "$HOME/.config/opencode/slim-router.json" && ok 'bestehende Config erhalten' || bad 'Config wurde ueberschrieben'

echo "== uninstall.sh =="
bash "$ROOT/uninstall.sh" >/dev/null 2>&1 && ok 'uninstall.sh Lauf' || bad 'uninstall.sh fehlgeschlagen'
[ ! -e "$HOME/.local/bin/ananta-cockpit" ] && ok 'Wrapper entfernt' || bad 'Wrapper verblieben'
[ ! -e "$HOME/.config/opencode/plugins/slim-router.ts" ] && ok 'Plugin entfernt' || bad 'Plugin verblieben'
[ -f "$HOME/.config/opencode/slim-router.json" ] && ok 'Config bewusst erhalten' || bad 'Config wurde geloescht'

echo "== status-click.sh =="
# Nach Deinstallation erneut installieren fuer den Klicktest.
bash "$ROOT/install.sh" >/dev/null 2>&1
SC="$XDG_DATA_HOME/ananta-cockpit/status-click.sh"
export TMUX="/tmp/fake-socket,\$0,0"   # nur fuer den Guard; display-popup wird fehlschlagen
for range in ac0 ac1 ac2 ac3 ac4 ac5 ac6; do
  "$SC" "$range" 'ses_test' /tmp "$XDG_DATA_HOME/ananta-cockpit" >/dev/null 2>&1
  [ $? = 0 ] && ok "range $range akzeptiert (rc=0)" || bad "range $range rc!=0"
done
"$SC" 'other-range' 'ses_test' /tmp "$XDG_DATA_HOME/ananta-cockpit" >/dev/null 2>&1
[ $? = 0 ] && ok 'unbekannter Bereich = no-op' || bad 'unbekannter Bereich rc!=0'
[ -f "$XDG_STATE_HOME/ananta-cockpit/status-click.log" ] && ok 'Log geschrieben' || bad 'Log fehlt'

echo "== Plugin-Sicherheitsregression =="
grep -q 'export default SlimRouter' "$ROOT/slim-router/slim-router.ts" && ok 'Plugin-Export (Quelle)' || bad 'Plugin-Export fehlt (Quelle)'
if grep -q '"plugin": \["list"\]' "$REAL_HOME/.config/opencode/opencode.json" 2>/dev/null; then
  bad 'bekannter Fehler plugin:["list"] ist wieder vorhanden!'
else
  ok 'plugin:["list"]-Fehler nicht vorhanden'
fi
if grep -qEi 'apikey|api_key|secret|password' "$ROOT/cockpit/status-click.sh" "$ROOT/install.sh"; then
  bad 'Quellen enthalten moegliche Geheimnisse'
else
  ok 'keine Geheimnisse in Quellen'
fi
# Muster dynamisch aufbauen, damit sich der Test nicht selbst matcht.
TOKPAT='gh'"p_"'|gh'"o_"'|gith'"ub_pat_"'|sk-[A-Za-z0-9]{20}'
if grep -rqE "$TOKPAT" "$ROOT" --include='*.py' --include='*.ts' --include='*.sh' --include='*.json' 2>/dev/null; then
  bad 'Repo enthaelt Token-Muster!'
else
  ok 'keine Token-Muster im Repo'
fi

rm -rf "$FAKE"
echo
echo "Ergebnis: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
