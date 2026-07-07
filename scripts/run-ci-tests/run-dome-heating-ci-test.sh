#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "--- Running Dome Heating Unit Tests ---"
cd "$REPO_ROOT"
"${PYTHON:-python}" -m pytest -v -s --maxfail=2 tests/dome_heating/

echo "--- Dome Heating CI Run Completed Successfully ---"
