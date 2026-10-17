#!/usr/bin/env bash
# Compatibility entry point: RANGE SESSION PROJECT ROOT [left|right].
# Alte Bereiche ac0..ac7 oeffnen die klassischen Aktions-Popups; die neuen
# Statusleisten-Bereiche menu-*/chat-* werden an status.py delegiert.
set -u
range="${1:-}"; sid="${2:-}"; project="${3:-$PWD}"
root="${4:-$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)}"
button="${5:-left}"
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
  ac6) action=codecompass ;;
  ac7) action=logs ;;
  menu-*|chat-*)
    exec python3 "$root/status.py" click "$range" "$sid" "$button"
    ;;
  *)
    log "noop range=$range sid=$sid"
    exit 0
    ;;
esac

log "click action=$action range=$range sid=$sid"
if [[ -z "$sid" || -z "${TMUX:-}" || ! -e "$root/cockpit" ]]; then
  log "skip action=$action reason=missing-args range=$range sid=$sid root=$root"
  exit 0
fi
# Aktion in einem separaten Popup starten; Fehler werden protokolliert.
tmux display-popup -t "$sid" -E -w 85% -h 75% -d "$project" \
  "bash \"$root/cockpit\" action $action \"$project\"" \
  || log "popup-failed action=$action"
exit 0
