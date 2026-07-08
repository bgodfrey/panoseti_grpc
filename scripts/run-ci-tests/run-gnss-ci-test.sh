#!/bin/bash
set -e

PSETI_GRPC="${PSETI_GRPC:-pseti-grpc}"
PYTHON="${PYTHON:-python}"
GNSS_DIR="gnss_config/U-Blox_F9T_Config"
GNSS_CONFIG="$GNSS_DIR/gnss_scripts/gnss_deployment.json5"

echo "--- Running GNSS CLI Smoke Tests ---"

# Confirm the GNSS orchestrator submodule is present. This catches checkouts
# that forgot `git submodule update --init --recursive`.
test -f "$GNSS_DIR/gnss_scripts/gnss_orchestrator.py"

# Exercise the pseti-grpc passthrough without touching hardware, SSH, Redis, or
# screen sessions. These commands should be stable in CI because they only ask
# argparse to render the available GNSS orchestrator commands.
"$PSETI_GRPC" gnss --help
"$PSETI_GRPC" gnss status --help
"$PSETI_GRPC" gnss start --help
"$PSETI_GRPC" gnss stop --help

# Validate that the deployment inventory remains parseable JSON5. The full
# status command is intentionally not used here because it checks local Palomar
# deployment paths that are not expected to exist on CI runners.
"$PYTHON" -c "import json5; json5.load(open('$GNSS_CONFIG')); print('gnss json5 ok')"

echo "--- GNSS CLI Smoke Tests Completed Successfully ---"
