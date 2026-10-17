#!/usr/bin/env bash
# Ananta OpenCode Cockpit – einheitliche, idempotente Installation.
#
#   cockpit/      tmux-Oberflaeche   -> ~/.local/share/ananta-cockpit/ + ~/.local/bin/ananta-cockpit
#   oc-side/      Side-Chat-Popups   -> ~/.local/bin/oc-side
#   oc-side-sync/ Kontext-Sync       -> ~/.local/bin/oc-side-sync
#   oc-codecompass/ Hub-MCP-Anbindung -> ~/.local/bin/oc-codecompass
#   slim-router/  OpenCode-Plugins   -> ~/.config/opencode/plugins/ (+ Configs)
#                   slim-plan CLI    -> ~/.local/bin/slim-plan
#
# Aufruf aus beliebigem Arbeitsverzeichnis moeglich. Mehrfach ausfuehrbar.
# Vorhandene Dateien werden nach ~/.local/share/ananta-cockpit/backups/<stamp>/ gesichert.
set -euo pipefail

SRC="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/ananta-cockpit"
BIN="$HOME/.local/bin"
OC="${OC_CONFIG_DIR:-$HOME/.config/opencode}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$SHARE/backups/$STAMP"

command -v tmux >/dev/null || { echo 'Fehlt: tmux (sudo apt install tmux)'; exit 1; }
command -v python3 >/dev/null || { echo 'Fehlt: python3'; exit 1; }

mkdir -p "$SHARE" "$BIN" "$BACKUP" "$OC/plugins"

backup() {
  if [ -e "$1" ]; then
    cp -p -- "$1" "$BACKUP/$2"
  fi
}

# --- 1. Cockpit -------------------------------------------------------------
for f in tmux_setup.py actions.py sidebar.py status-click.sh cockpit; do
  backup "$SHARE/$f" "$f"
done
install -m 644 "$SRC/cockpit/tmux_setup.py" "$SHARE/tmux_setup.py"
install -m 644 "$SRC/cockpit/actions.py" "$SHARE/actions.py"
install -m 644 "$SRC/cockpit/sidebar.py" "$SHARE/sidebar.py"
install -m 755 "$SRC/cockpit/status-click.sh" "$SHARE/status-click.sh"
install -m 755 "$SRC/cockpit/cockpit" "$SHARE/cockpit"

# Wrapper: erst alte Datei/Symlink entfernen, sonst schreibt cat > durch Symlinks.
backup "$BIN/ananta-cockpit" "bin-ananta-cockpit"
rm -f -- "$BIN/ananta-cockpit"
printf '#!/usr/bin/env bash\nexec bash "%s/cockpit" "$@"\n' "$SHARE" > "$BIN/ananta-cockpit"
chmod 755 "$BIN/ananta-cockpit"

# Sanity: SHARE/cockpit darf kein Self-Wrapper sein.
if grep -q "exec bash \"$SHARE/cockpit\"" "$SHARE/cockpit"; then
  echo "FEHLER: $SHARE/cockpit ist beschaedigt (Self-Wrapper)." >&2
  exit 1
fi

# Veraltete flache Kopien in ~/.local/bin entfernen (Backup liegt in $BACKUP).
for f in tmux_setup.py actions.py sidebar.py status-click.sh; do
  [ -f "$BIN/$f" ] && [ ! -L "$BIN/$f" ] && rm -f -- "$BIN/$f"
done

# --- 2. oc-side -------------------------------------------------------------
backup "$BIN/oc-side" "bin-oc-side"
install -m 755 "$SRC/oc-side/oc-side" "$BIN/oc-side"

# --- 3. oc-side-sync --------------------------------------------------------
backup "$BIN/oc-side-sync" "bin-oc-side-sync"
install -m 755 "$SRC/oc-side-sync/side-sync.py" "$SHARE/side-sync.py"
rm -f -- "$BIN/oc-side-sync"
printf '#!/usr/bin/env bash\nexec python3 "%s/side-sync.py" "$@"\n' "$SHARE" > "$BIN/oc-side-sync"
chmod 755 "$BIN/oc-side-sync"

# --- 4. slim-plan -----------------------------------------------------------
backup "$BIN/slim-plan" "bin-slim-plan"
install -m 755 "$SRC/slim-router/planctl.py" "$BIN/slim-plan"

# --- 4b. oc-codecompass ------------------------------------------------------
backup "$BIN/oc-codecompass" "bin-oc-codecompass"
install -m 755 "$SRC/oc-codecompass/oc-codecompass" "$BIN/oc-codecompass"
CC_CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ananta-cockpit"
mkdir -p "$CC_CFG_DIR"
if [ ! -f "$CC_CFG_DIR/codecompass.json" ]; then
  printf '{\n  "hub_url": "http://127.0.0.1:5000",\n  "server_name": "ananta_codecompass"\n}\n' \
    > "$CC_CFG_DIR/codecompass.json"
  echo "CodeCompass-Konfiguration angelegt: $CC_CFG_DIR/codecompass.json"
fi

# --- 5. OpenCode-Plugins und Configs (Backups, Schluessel bleiben unangetastet) --
for f in slim-router.ts context-manager.ts; do
  backup "$OC/plugins/$f" "plugins-$f"
  install -m 644 "$SRC/slim-router/$f" "$OC/plugins/$f"
done
for f in slim-router.json slim-context.json; do
  backup "$OC/$f" "config-$f"
  if [ ! -f "$OC/$f" ]; then
    install -m 644 "$SRC/slim-router/$f" "$OC/$f"
  else
    echo "Bestehende Config erhalten: $OC/$f (Vorlage liegt in slim-router/$f)"
  fi
done

echo "Installiert nach: $SHARE"
echo "Aufruf:           $BIN/ananta-cockpit"
echo "Backups:          $BACKUP"
echo
echo 'Start in tmux:  tmux new -s ananta   # falls nicht bereits in tmux'
echo '                ananta-cockpit start ~/ananta'
echo 'Stop:           ananta-cockpit stop'
echo "PATH-Hinweis:   export PATH=\"\$HOME/.local/bin:\$PATH\""
echo 'Plugin-Aenderungen wirken nach OpenCode-Neustart.'
echo 'Deinstallation: bash uninstall.sh'
