#!/usr/bin/env bash
# tmux-Mausklick auf die Ananta-Statusleiste.
# Parameter: <mouse_status_range> <session_id> <projekt> <root>
# Reagiert NUR auf die Bereiche ac0..ac6 – alle anderen Klicks sind no-ops.
set -u
range="${1:-}"; sid="${2:-}"; project="${3:-$PWD}"; root="${4:-}"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/ananta-cockpit"
LOG="$STATE/status-click.log"
mkdir -p "$STATE"
log() { printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG" 2>/dev/null || true; }

case "$range" in
  ac0) action=side ;;
  ac1) action=sessions ;;
  ac2) action=models ;;
  ac3) action=plans ;;
  ac4) action=sync ;;
  ac5) action=router ;;
  ac6) action=logs ;;
  *) exit 0 ;;
esac

if [[ -z "$root" || -z "$sid" ]]; then
  log "skip action=$action reason=missing-args range=$range sid=$sid root=$root"
  exit 0
fi
if [[ ! -x "$root/cockpit" && ! -f "$root/cockpit" ]]; then
  log "error action=$action reason=cockpit-missing root=$root"
  exit 1
fi
if [[ -z "${TMUX:-}" ]]; then
  log "error action=$action reason=not-in-tmux"
  exit 1
fi

log "click action=$action range=$range sid=$sid"
# Aktion in einem separaten Popup starten; Fehler werden protokolliert.
tmux display-popup -t "$sid" -E -w 85% -h 75% -d "$project" \
  "bash \"$root/cockpit\" action $action \"$project\""
rc=$?
if [ "$rc" -ne 0 ]; then
  log "popup-failed action=$action rc=$rc"
fi
exit 0
