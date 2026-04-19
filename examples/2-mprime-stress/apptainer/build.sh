#!/usr/bin/env bash
# Build mprime-stress.sif. Runs from the repo root so %files paths in
# the .def can reference cpu_thermals/, pyproject.toml, and examples/2-...
# directly. Requires apptainer 1.x on PATH.
#
# Note: the build downloads mprime (~10 MB) once; the image bakes it
# in so runtime works on offline compute nodes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../.."   # repo root
exec apptainer build --force \
    "$HERE/mprime-stress.sif" \
    "$HERE/mprime-stress.def"
