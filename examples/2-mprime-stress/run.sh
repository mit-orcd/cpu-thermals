#!/usr/bin/env bash
#
# Run an mprime torture test while cpu_thermals records temperatures.
#
# Produces  results/<timestamp>/temps.csv   (one row per sensor sample)
#           results/<timestamp>/phases.csv  (start/end of each load phase)
#
# Phases (auto-selected from lscpu output):
#   1 socket  -> "all-cores"
#   2 sockets -> "socket-0", "socket-1", "all-sockets"
#
# Tunables (env vars):
#   DURATION         seconds per phase             (default 10)
#   SAMPLE_INTERVAL  cpu_thermals refresh seconds  (default 0.5)
#   OUTPUT_DIR       output directory              (default ./results/<ts>)
#   MPRIME_URL       override the download URL     (default upstream)
#
# Linux requires `taskset` (util-linux). macOS uses `gtimeout` from
# coreutils (`brew install coreutils`); Linux already ships `timeout`.

set -euo pipefail

DURATION="${DURATION:-10}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.5}"
OUTPUT_DIR="${OUTPUT_DIR:-./results/$(date +%Y%m%d-%H%M%S)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MPRIME_DIR="$SCRIPT_DIR/mprime"
MPRIME_BIN="mprime"

# ---------------------------------------------------------------- platform

PLATFORM="$(uname -s)-$(uname -m)"
case "$PLATFORM" in
    Linux-x86_64)
        MPRIME_URL="${MPRIME_URL:-https://www.mersenne.org/download/software/v30/30.19/p95v3019b20.linux64.tar.gz}"
        ;;
    Darwin-arm64|Darwin-x86_64)
        MPRIME_URL="${MPRIME_URL:-https://www.mersenne.org/download/software/v30/30.19/p95v3019b20.MacOSX.tar.gz}"
        ;;
    *)
        echo "error: unsupported platform: $PLATFORM" >&2
        echo "Set MPRIME_URL manually if you have a build for your platform." >&2
        exit 1
        ;;
esac

# Pick a `timeout` implementation (Linux: timeout; macOS: gtimeout).
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout"
else
    echo "error: need 'timeout' (Linux) or 'gtimeout' (macOS: brew install coreutils)" >&2
    exit 1
fi

if ! command -v cpu-thermals >/dev/null 2>&1; then
    echo "error: 'cpu-thermals' is not on PATH. See ../../README.md for install." >&2
    exit 1
fi

# ---------------------------------------------------------------- mprime

if [[ ! -x "$MPRIME_DIR/$MPRIME_BIN" ]]; then
    echo ">> Downloading mprime for $PLATFORM ..."
    mkdir -p "$MPRIME_DIR"
    curl -fL "$MPRIME_URL" -o "$MPRIME_DIR/mprime.tar.gz"
    tar -xzf "$MPRIME_DIR/mprime.tar.gz" -C "$MPRIME_DIR"
    rm -f "$MPRIME_DIR/mprime.tar.gz"
    chmod +x "$MPRIME_DIR/$MPRIME_BIN"
fi

# Generate the headless torture-test config. mprime reads local.txt + prime.txt
# from the working dir given by `-W` and runs without prompting when
# StressTester=1 is set in local.txt.
write_mprime_config() {
    local threads="$1"
    cat > "$MPRIME_DIR/local.txt" <<EOF
V24OptionsConverted=1
V30OptionsConverted=1
WGUID_version=2
StressTester=1
UsePrimenetServer=0
WorkerThreads=$threads
EOF
    cat > "$MPRIME_DIR/prime.txt" <<EOF
TortureType=12
TortureThreads=$threads
TortureMem=0
TortureTime=1
EOF
}

# ---------------------------------------------------------------- topology

if command -v lscpu >/dev/null 2>&1; then
    SOCKETS=$(lscpu | awk -F: '/^Socket\(s\):/ {gsub(/ /,"",$2); print $2}')
    TOTAL_CPUS=$(nproc)
else
    SOCKETS=1
    TOTAL_CPUS=$(sysctl -n hw.physicalcpu 2>/dev/null || echo 1)
fi
SOCKETS="${SOCKETS:-1}"

echo ">> Detected: $SOCKETS socket(s), $TOTAL_CPUS logical CPU(s)"

# ---------------------------------------------------------------- output

mkdir -p "$OUTPUT_DIR"
TEMPS_CSV="$OUTPUT_DIR/temps.csv"
PHASE_LOG="$OUTPUT_DIR/phases.csv"
echo "phase,start_iso,end_iso" > "$PHASE_LOG"

# ---------------------------------------------------------------- recorder

echo ">> Starting cpu-thermals --csv $TEMPS_CSV --no-tui (interval ${SAMPLE_INTERVAL}s)"
cpu-thermals "$SAMPLE_INTERVAL" --csv "$TEMPS_CSV" --no-tui &
CT_PID=$!

cleanup() {
    if kill -0 "$CT_PID" 2>/dev/null; then
        kill -INT "$CT_PID" 2>/dev/null || true
        wait "$CT_PID" 2>/dev/null || true
    fi
    pkill -f "$MPRIME_DIR/$MPRIME_BIN" 2>/dev/null || true
}
trap cleanup EXIT

sleep 1   # short baseline before the first phase

# ---------------------------------------------------------------- phases

# Cross-platform ISO 8601 timestamp with timezone offset (e.g. 2026-04-18T11:43:57-04:00).
iso_now() {
    if date --version >/dev/null 2>&1; then
        date -Iseconds              # GNU date (Linux)
    else
        date "+%Y-%m-%dT%H:%M:%S%z" | sed 's/\(..\)$/:\1/'   # BSD date (macOS)
    fi
}

phase() {
    local name="$1"; shift
    local start_iso end_iso
    start_iso=$(iso_now)
    echo ">> Phase '$name' (${DURATION}s): $*"
    ( "$@" ) </dev/null >/dev/null 2>&1 || true
    end_iso=$(iso_now)
    echo "$name,$start_iso,$end_iso" >> "$PHASE_LOG"
    sleep 2   # brief cool-down between phases
}

if [[ "$SOCKETS" -ge 2 ]] && command -v taskset >/dev/null 2>&1; then
    # Per-socket pinning, then both sockets together.
    for s in $(seq 0 $((SOCKETS - 1))); do
        cores=$(lscpu -p=cpu,socket | awk -F, -v s="$s" '!/^#/ && $2==s {print $1}' | paste -sd, -)
        n_cores=$(echo "$cores" | tr , '\n' | wc -l | tr -d ' ')
        write_mprime_config "$n_cores"
        phase "socket-$s" "$TIMEOUT_CMD" "$DURATION" taskset -c "$cores" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
    done
    write_mprime_config "$TOTAL_CPUS"
    phase "all-sockets" "$TIMEOUT_CMD" "$DURATION" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
else
    # Single-socket (or macOS) -> one combined phase.
    write_mprime_config "$TOTAL_CPUS"
    phase "all-cores" "$TIMEOUT_CMD" "$DURATION" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
fi

echo ">> Done. Results in: $OUTPUT_DIR"
echo "    temps.csv  - one row per sensor sample"
echo "    phases.csv - one row per phase (join on timestamp)"
