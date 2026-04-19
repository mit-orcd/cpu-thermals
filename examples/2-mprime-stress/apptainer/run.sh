#!/usr/bin/env bash
# Run the built mprime-stress.sif. Forwards any args (none expected
# under default usage; use env vars like DURATION=30 to tune).
# Results are written to $PWD/results/<timestamp>/ on the host.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/mprime-stress.sif" ]] \
    || { echo "build first: $HERE/build.sh" >&2; exit 1; }
exec apptainer run "$HERE/mprime-stress.sif" "$@"
