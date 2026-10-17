#!/usr/bin/env bash
# Startet den vollstaendigen Ananta-Cockpit-Testlauf.
# Reihenfolge: Python-Unit/Integration -> Bun (Router) -> Bash-Regression.
set -u
HERE="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
ROOT="$(dirname "$HERE")"
FAIL=0

echo "########## Python-Tests (pytest/unittest) ##########"
if python3 -m pytest --version >/dev/null 2>&1; then
  ( cd "$ROOT" && python3 -m pytest tests/ -q ) || FAIL=1
elif command -v uv >/dev/null; then
  ( cd "$ROOT" && uv run --with pytest python -m pytest tests/ -q ) || FAIL=1
else
  echo "Weder pytest noch uv gefunden – bitte 'pip install pytest' oder uv installieren."
  FAIL=1
fi

echo
echo "########## Bun: slim-router ##########"
if command -v bun >/dev/null; then
  ( cd "$HERE/.." && bun test ./tests/ ) || FAIL=1
else
  echo "bun nicht gefunden – Router-Tests uebersprungen (nicht bestanden)."
  FAIL=1
fi

echo
echo "########## Bash-Regression ##########"
bash "$HERE/test_install.sh" || FAIL=1
bash "$HERE/test_up.sh" || FAIL=1

echo
if [ "$FAIL" = 0 ]; then
  echo "ALLE TESTS BESTANDEN."
else
  echo "TESTS FEHLGESCHLAGEN."
fi
exit "$FAIL"
