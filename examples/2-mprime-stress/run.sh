#!/usr/bin/env bash
#
# Run an mprime torture test while cpu_thermals records temperatures.
#
# Produces  results/<timestamp>/temps.csv   (one row per sensor sample)
#           results/<timestamp>/phases.csv  (start/end of each load phase)
#
# Phases (auto-selected from /proc/cpuinfo topology):
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
# MPRIME_DIR defaults to a directory next to this script. Override (e.g.
# MPRIME_DIR=$HOME/.cache/cpu-thermals-mprime) for read-only checkouts
# or shared workstations.
MPRIME_DIR="${MPRIME_DIR:-$SCRIPT_DIR/mprime}"
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

# Make sure MPRIME_DIR is writable BEFORE we do anything that needs it.
# Read-only checkouts and shared workstations are common; surfacing the
# failure here (rather than mid-download) keeps the error message
# actionable. Skipped silently if the dir already contains a usable
# mprime binary -- nothing to write.
if [[ ! -x "$MPRIME_DIR/$MPRIME_BIN" ]]; then
    if ! mkdir -p "$MPRIME_DIR" 2>/dev/null \
        || ! ( : > "$MPRIME_DIR/.write_check" ) 2>/dev/null; then
        echo "error: MPRIME_DIR ($MPRIME_DIR) is not writable." >&2
        echo "       Set MPRIME_DIR to a writable path, e.g.:" >&2
        echo "           MPRIME_DIR=\$HOME/.cache/cpu-thermals-mprime ./run.sh" >&2
        exit 1
    fi
    rm -f "$MPRIME_DIR/.write_check"

    echo ">> Downloading mprime for $PLATFORM into $MPRIME_DIR ..."
    if ! curl -fL "$MPRIME_URL" -o "$MPRIME_DIR/mprime.tar.gz"; then
        echo "error: download from $MPRIME_URL failed (no network? blocked egress?)." >&2
        echo "       Either fix connectivity, or pre-place an mprime binary at" >&2
        echo "       $MPRIME_DIR/$MPRIME_BIN and re-run." >&2
        exit 1
    fi
    tar -xzf "$MPRIME_DIR/mprime.tar.gz" -C "$MPRIME_DIR"
    rm -f "$MPRIME_DIR/mprime.tar.gz"
    chmod +x "$MPRIME_DIR/$MPRIME_BIN"
fi

# Generate the headless torture-test config. mprime reads local.txt + prime.txt
# from the working dir given by `-W` and runs without prompting when
# StressTester=1 is set in local.txt.
#
# EnableSetAffinity=0 is critical: by default mprime calls
# sched_setaffinity() per worker thread, overriding any process-level
# mask set by `taskset`.  Disabling it lets the inherited taskset mask
# govern which CPUs the workers can run on.
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
EnableSetAffinity=0
AffinityVerbosityTorture=1
EOF
}

# ---------------------------------------------------------------- topology
#
# On Linux, derive socket count and per-socket CPU lists from
# /proc/cpuinfo — the authoritative kernel interface for processor,
# physical id, and core id.  On macOS (no /proc/cpuinfo) fall back to
# sysctl; multi-socket pinning is not attempted there anyway.

# Emit "processor physical_id core_id" triples, one per logical CPU.
_cpuinfo_topology() {
    awk '
        /^processor/   { p = $NF }
        /^physical id/ { s = $NF }
        /^core id/     { print p, s, $NF }
    ' /proc/cpuinfo
}

# All logical CPUs on socket $1 (comma-separated, sorted numerically).
_cpus_on_socket() {
    _cpuinfo_topology | awk -v s="$1" '$2 == s { print $1 }' \
        | sort -n | paste -sd, -
}

# One logical CPU per physical core on socket $1.
# Picks the first processor seen for each unique (physical_id, core_id).
_one_per_core_on_socket() {
    _cpuinfo_topology | awk -v s="$1" '
        $2 == s {
            key = $2 ":" $3
            if (!(key in seen)) { seen[key] = 1; print $1 }
        }
    ' | sort -n | paste -sd, -
}

if [[ -f /proc/cpuinfo ]]; then
    SOCKETS=$(_cpuinfo_topology | awk '{ print $2 }' | sort -un | wc -l)
    TOTAL_CPUS=$(nproc)
else
    # macOS — no /proc/cpuinfo, no multi-socket pinning.
    SOCKETS=1
    TOTAL_CPUS=$(sysctl -n hw.physicalcpu 2>/dev/null || echo 1)
fi
SOCKETS="${SOCKETS:-1}"

echo ">> Detected: $SOCKETS socket(s), $TOTAL_CPUS logical CPU(s)"

# ---------------------------------------------------------------- output

mkdir -p "$OUTPUT_DIR"
TEMPS_CSV="$OUTPUT_DIR/temps.csv"
PHASE_LOG="$OUTPUT_DIR/phases.csv"
# phases.csv schema: phase,start_iso,end_iso,status
# `status` is "ok" for clean / timeout-killed runs; "FAILED:exit=N" for
# anything else. Surfaces real stress failures that the old `|| true`
# pattern silently swallowed.
echo "phase,start_iso,end_iso,status" > "$PHASE_LOG"

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
    local start_iso end_iso rc status
    start_iso=$(iso_now)
    echo ">> Phase '$name' (${DURATION}s): $*"

    # Capture the underlying command's exit code without aborting the run.
    # `timeout` returns 124 when it had to SIGTERM the child (which is
    # our expected case for an infinite-running mprime); 137 if it had
    # to SIGKILL after the grace period; 143 if the child caught SIGTERM
    # and exited cleanly. Any other non-zero is a real failure (bad
    # taskset mask, missing exec bit, broken mprime, etc.) and we want
    # to know -- the previous `|| true` swallowed everything and gave
    # false confidence.
    rc=0
    ( "$@" ) </dev/null >/dev/null 2>&1 || rc=$?
    end_iso=$(iso_now)

    case "$rc" in
        0|124|137|143)
            status="ok"
            ;;
        *)
            status="FAILED:exit=$rc"
            echo "!! Phase '$name' FAILED (exit code $rc); continuing." >&2
            echo "   To debug, re-run the inner command directly:" >&2
            echo "       $*" >&2
            ;;
    esac

    echo "$name,$start_iso,$end_iso,$status" >> "$PHASE_LOG"
    sleep 2   # brief cool-down between phases
}

if [[ "$SOCKETS" -ge 2 ]] && command -v taskset >/dev/null 2>&1; then
    # Per-socket pinning, then both sockets together.
    # WorkerThreads = physical cores (one FFT worker per core; running
    # two workers per SMT pair adds scheduling overhead with negligible
    # extra thermal stress).  The taskset mask includes all logical CPUs
    # on the socket so the OS scheduler still has SMT freedom.
    total_phys=0
    for s in $(seq 0 $((SOCKETS - 1))); do
        all_cpus=$(_cpus_on_socket "$s")
        n_phys=$(_one_per_core_on_socket "$s" | tr , '\n' | wc -l | tr -d ' ')
        total_phys=$((total_phys + n_phys))
        write_mprime_config "$n_phys"
        phase "socket-$s" "$TIMEOUT_CMD" "$DURATION" taskset -c "$all_cpus" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
    done
    write_mprime_config "$total_phys"
    phase "all-sockets" "$TIMEOUT_CMD" "$DURATION" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
else
    # Single-socket (or macOS) -> one combined phase.
    if [[ -f /proc/cpuinfo ]]; then
        n_phys=$(_one_per_core_on_socket 0 | tr , '\n' | wc -l | tr -d ' ')
    else
        # macOS sysctl hw.physicalcpu already excludes SMT.
        n_phys="$TOTAL_CPUS"
    fi
    write_mprime_config "$n_phys"
    phase "all-cores" "$TIMEOUT_CMD" "$DURATION" "$MPRIME_DIR/$MPRIME_BIN" -t -W "$MPRIME_DIR"
fi

echo ">> Done. Results in: $OUTPUT_DIR"
echo "    temps.csv  - one row per sensor sample"
echo "    phases.csv - one row per phase (join on timestamp)"
