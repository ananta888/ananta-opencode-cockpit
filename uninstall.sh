#!/usr/bin/env bash
# Ananta OpenCode Cockpit – vollstaendige Deinstallation.
# Entfernt nur Dateien dieses Projekts; andere Plugins/Konfigurationen bleiben.
# Vorhandene Configs werden NICHT geloescht, sondern nur die eigenen Schriften.
set -euo pipefail

SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/ananta-cockpit"
BIN="$HOME/.local/bin"
OC="${OC_CONFIG_DIR:-$HOME/.config/opencode}"

remove() {
  if [ -e "$1" ] || [ -L "$1" ]; then
    rm -f -- "$1" && echo "entfernt: $1"
  fi
}

echo 'Ananta OpenCode Cockpit deinstallieren?'

remove "$BIN/ananta-cockpit"
remove "$BIN/oc-side"
remove "$BIN/oc-side-sync"
remove "$BIN/oc-codecompass"
remove "$BIN/slim-plan"
# Veraltete flache Kopien.
for f in tmux_setup.py actions.py sidebar.py status-click.sh; do
  remove "$BIN/$f"
done

remove "$OC/plugins/slim-router.ts"
remove "$OC/plugins/context-manager.ts"

# Configs bleiben erhalten (koennen eigene Anpassungen enthalten).
for f in slim-router.json slim-context.json; do
  if [ -f "$OC/$f" ]; then
    echo "erhalten (nicht geloescht): $OC/$f"
  fi
done

if [ -d "$SHARE" ]; then
  echo "Runtime-Dateien/Backups bleiben liegen: $SHARE"
  echo "  (fuer vollstaendige Entfernung: rm -rf \"$SHARE\")"
fi

echo 'Hinweis: die tmux-Mausbindung entfernen, falls gesetzt:'
echo '  tmux unbind-key -T root MouseDown1Status'
echo 'Fertig.'
