#!/usr/bin/env bash
# Startet den vollstaendigen Ananta-Cockpit-Testlauf.
# Reihenfolge: Python-Unit/Integration -> Bun (Router) -> Bash-Regression.
set -u
HERE="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
FAIL=0

echo "########## Python unittest ##########"
python3 -m unittest discover -s "$HERE" -p 'test_*.py' -v || FAIL=1

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

echo
if [ "$FAIL" = 0 ]; then
  echo "ALLE TESTS BESTANDEN."
else
  echo "TESTS FEHLGESCHLAGEN."
fi
exit "$FAIL"
