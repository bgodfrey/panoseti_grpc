#!/bin/bash
set -e

PSETI_GRPC="${PSETI_GRPC:-pseti-grpc}"
PYTHON="${PYTHON:-python}"
echo "--- Running GNSS CLI Smoke Tests ---"

# The GNSS extra supplies the independent receiver package. PANOSETI telemetry
# is connected through a package entry point rather than a nested submodule.
"$PYTHON" -c "import ublox_f9t"
"$PYTHON" -c "from importlib.metadata import entry_points; assert any(ep.name == 'panoseti' for ep in entry_points(group='ublox_f9t.status_publishers'))"

# Exercise the pseti-grpc passthrough without touching hardware, SSH, Redis, or
# screen sessions. These commands should be stable in CI because they only ask
# argparse to render the available GNSS orchestrator commands.
"$PSETI_GRPC" gnss --help
"$PSETI_GRPC" gnss status --help
"$PSETI_GRPC" gnss start --help
"$PSETI_GRPC" gnss stop --help
"$PSETI_GRPC" gnss detect --help

echo "--- GNSS CLI Smoke Tests Completed Successfully ---"
