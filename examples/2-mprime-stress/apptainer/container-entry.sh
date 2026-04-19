#!/usr/bin/env bash
#
# In-image entrypoint for the mprime-stress.sif container.
#
# Why this shim exists:
#   The upstream examples/2-mprime-stress/run.sh writes mprime config
#   files (prime.txt, local.txt) next to the mprime binary at runtime,
#   so its layout requires a writable mprime/ directory beside the
#   script. SIFs are read-only at runtime, so /opt/stress/mprime/
#   inside the image cannot be written to.
#
#   This shim copies the baked-in /opt/stress tree into a writable
#   tmpdir under $PWD (which Apptainer auto-mounts from the host),
#   then cd's there and exec's the upstream run.sh unchanged. Results
#   land in $PWD/results/<timestamp>/ per upstream defaults.
#
# Net effect: the bare-metal run.sh stays untouched, and this is the
# only Apptainer-specific bit of code.
#
set -euo pipefail

WORK="$(mktemp -d "${PWD}/cpu-thermals-stress-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

cp -a /opt/stress/. "$WORK/"
cd "$WORK"
exec ./run.sh "$@"
