#!/usr/bin/env bash
# Regressionstests fuer "ananta-cockpit up": Argumente, Dry-Run und ein
# echtes tmux-E2E mit Stubs (kein Netz, kein LLM, kein echter opencode).
set -u
ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/.." && pwd)"
FAKE="$(mktemp -d /tmp/ac-up-test.XXXXXX)"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok   - $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL - $1"; }

COCKPIT="bash $ROOT/cockpit/cockpit"

echo "== up: Argumente und Validation =="
$COCKPIT help | grep -q ' up \[' && ok 'help nennt up' || bad 'help nennt up nicht'
$COCKPIT up --help >/dev/null 2>&1 && ok 'up --help rc=0' || bad 'up --help rc!=0'
$COCKPIT up /nonexistent --dry-run >/dev/null 2>&1
[ $? = 2 ] && ok 'fehlendes Verzeichnis rc=2' || bad 'fehlendes Verzeichnis rc!=2'
$COCKPIT up --bogus /tmp >/dev/null 2>&1
[ $? = 2 ] && ok 'unbekannte Option rc=2' || bad 'unbekannte Option rc!=2'
$COCKPIT up /tmp /var >/dev/null 2>&1
[ $? = 2 ] && ok 'zwei Projekte rc=2' || bad 'zwei Projekte rc!=2'
$COCKPIT up /tmp -m >/dev/null 2>&1
[ $? = 2 ] && ok '--model ohne Wert rc=2' || bad '--model ohne Wert rc!=2'
$COCKPIT up /tmp -s >/dev/null 2>&1
[ $? = 2 ] && ok '--session ohne Wert rc=2' || bad '--session ohne Wert rc!=2'

echo "== up: Dry-Run (ausserhalb tmux) =="
out=$(env -u TMUX $COCKPIT up /tmp --dry-run 2>&1)
rc=$?
[ $rc = 0 ] && ok 'dry-run rc=0' || bad "dry-run rc=$rc"
grep -q 'tmux new-session -A -s tmp -c /tmp' <<<"$out" && ok 'tmux new-session Plan' || bad "Plan fehlt: $out"
grep -q -- '--pane' <<<"$out" && ok 'inner mit --pane' || bad 'inner ohne --pane'
grep -q 'tmux new-session -A -d -s' <<<"$(env -u TMUX $COCKPIT up /tmp --dry-run --detach 2>&1)" && ok '--detach im Plan' || bad '--detach fehlt im Plan'
grep -q -- '-m prov/mdl\|--model prov/mdl' <<<"$(env -u TMUX $COCKPIT up /tmp --dry-run -m prov/mdl 2>&1)" && ok 'Modell im Plan' || bad 'Modell fehlt im Plan'
grep -q -- '--no-mcp' <<<"$(env -u TMUX $COCKPIT up /tmp --dry-run --no-mcp 2>&1)" && ok '--no-mcp im Plan' || bad '--no-mcp fehlt im Plan'

echo "== up: Dry-Run (in tmux, ohne Ausfuehrung) =="
in=$(TMUX=/tmp/fake-socket,\$\$,0 $COCKPIT up /tmp --dry-run 2>&1)
grep -q 'tmux_setup start' <<<"$in" && ok 'Cockpit-Start angekuendigt' || bad 'Cockpit-Start fehlt'
grep -q 'oc-codecompass run' <<<"$in" && ok 'MCP-Start angekuendigt' || bad 'MCP-Start fehlt'
grep -q 'Rueckkehr' <<<"$in" && ok 'Rueckkehr-Pfad (nicht --pane)' || bad 'Rueckkehr-Pfad fehlt'
in=$(TMUX=/tmp/fake-socket,\$\$,0 $COCKPIT up /tmp --dry-run --no-mcp 2>&1)
grep -q 'opencode /tmp' <<<"$in" && ok 'opencode ohne MCP' || bad 'opencode ohne MCP fehlt'
in=$(TMUX=/tmp/fake-socket,\$\$,0 $COCKPIT up /tmp --dry-run --pane 2>&1)
grep -q 'Shell bleibt aktiv' <<<"$in" && ok 'pane-Modus haelt Shell' || bad 'pane-Modus fehlt'

echo "== up: echtes tmux-E2E mit Stubs =="
STUB="$FAKE/bin"; mkdir -p "$STUB" "$FAKE/proj"
: > "$FAKE/stub.log"
cat > "$STUB/oc-codecompass" <<EOF
#!/usr/bin/env bash
echo "oc:\$*" >> "$FAKE/stub.log"
case "\${1:-}" in status) exit 0;; run) exit 0;; esac
exit 0
EOF
cat > "$STUB/opencode" <<EOF
#!/usr/bin/env bash
echo "opencode:\$*" >> "$FAKE/stub.log"
exit 0
EOF
chmod +x "$STUB/oc-codecompass" "$STUB/opencode"
export TMUX_TMPDIR="$FAKE/tmuxsock"
mkdir -p "$TMUX_TMPDIR"
export XDG_STATE_HOME="$FAKE/state"

if env -u TMUX PATH="$STUB:$PATH" $COCKPIT up "$FAKE/proj" --detach -m prov/mdl >/dev/null 2>&1; then
  ok 'up --detach (ausserhalb tmux) rc=0'
else
  bad 'up --detach rc!=0'
fi
# warten bis der Stub-Run sichtbar ist
for _ in $(seq 1 40); do
  grep -q 'oc:run' "$FAKE/stub.log" 2>/dev/null && break
  sleep 0.25
done
grep -q 'oc:status' "$FAKE/stub.log" 2>/dev/null && ok 'Token-Check via oc-codecompass' || bad 'Token-Check fehlt'
grep -q "oc:run --model prov/mdl $FAKE/proj" "$FAKE/stub.log" 2>/dev/null && ok 'MCP-Run mit Modell+Projekt' || bad "MCP-Run fehlt: $(cat "$FAKE/stub.log" 2>/dev/null)"
tmux has-session 2>/dev/null && ok 'tmux-Session angelegt' || bad 'tmux-Session fehlt'
sidebar=$(tmux list-panes -a -F '#{pane_id}:#{@ananta_cockpit}' 2>/dev/null | grep -c ':1$')
[ "${sidebar:-0}" -ge 1 ] && ok 'Sidebar-Pane mit Marker' || bad "Sidebar-Pane fehlt ($sidebar)"
sid=$(tmux display-message -p '#{session_id}' 2>/dev/null || tmux list-sessions -F '#{session_id}' 2>/dev/null | head -1)
left=$(tmux show-options -t "$sid" status-left 2>/dev/null || true)
grep -q 'CODECOMPASS' <<<"$left" && ok 'Statusleiste zeigt CODECOMPASS' || bad "Statusleiste: $left"
grep -q 'SIDE' <<<"$left" && ok 'Statusleiste zeigt SIDE' || bad 'Statusleiste ohne SIDE'

# Zweiter Lauf: idempotent, --no-mcp -> direkter opencode-Stub
: > "$FAKE/stub.log"
if PATH="$STUB:$PATH" TMUX="$(tmux display-message -p '#{socket_path}'),$sid,0" \
   $COCKPIT up "$FAKE/proj" --detach --no-mcp >/dev/null 2>&1; then
  ok 'zweiter Lauf rc=0 (idempotent)' || true
else
  bad 'zweiter Lauf rc!=0'
fi
grep -q "opencode:$FAKE/proj" "$FAKE/stub.log" 2>/dev/null && ok '--no-mcp startet opencode direkt' || bad "opencode-Stub fehlt: $(cat "$FAKE/stub.log" 2>/dev/null)"
sidebar2=$(tmux list-panes -a -F '#{pane_id}:#{@ananta_cockpit}' 2>/dev/null | grep -c ':1$')
[ "${sidebar2:-0}" = "${sidebar:-1}" ] && ok 'keine doppelte Sidebar' || bad "Sidebar-Duplikat: $sidebar -> $sidebar2"

# Dritter Lauf: --detach auf EXISTENTER Session darf nicht attachen (TTY-Fehler)
out=$(PATH="$STUB:$PATH" TMUX="$(tmux display-message -p '#{socket_path}'),$sid,0" \
      $COCKPIT up "$FAKE/proj" --detach 2>&1)
rc=$?
[ $rc = 0 ] && ok 'detach auf existenter Session rc=0' || bad "detach-exist rc=$rc"
grep -q 'open terminal failed' <<<"$out" && bad 'detach hat angehaengt (TTY-Fehler)' || ok 'detach ohne Attach-Fehler'
grep -q 'laeuft bereits' <<<"$out" && ok 'Hinweis: Session laeuft bereits' || bad 'kein Laeuft-bereits-Hinweis'

tmux kill-server 2>/dev/null || true
rm -rf "$FAKE"
echo
echo "Ergebnis: $PASS bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = 0 ]
