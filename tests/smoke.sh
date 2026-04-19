#!/usr/bin/env bash
#
# Smoke tests for cpu_thermals.
#
# Usage:
#   ./tests/smoke.sh
#
# Each check prints "  ok    <name>" or "  FAIL  <name>". The script
# uses `set -e` so the first failing check stops the run with a
# non-zero exit code.
#
# No third-party packages are required. Just python3 and bash.

set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"   # so `python3 -m cpu_thermals` works without pip install

ok()      { printf "  ok    %s\n" "$1"; }
fail()    { printf "  FAIL  %s\n" "$1"; exit 1; }
section() { printf "\n== %s ==\n" "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT


# -------------------------------------------------------------- CLI args

section "CLI argument handling"

python3 -m cpu_thermals --help >/dev/null \
    || fail "--help should exit 0"
python3 -m cpu_thermals --help | grep -q -- "--csv" \
    || fail "--help should mention --csv"
python3 -m cpu_thermals --help | grep -q -- "--no-tui" \
    || fail "--help should mention --no-tui"
ok "--help works and lists --csv / --no-tui"

# `set -e` would abort on the expected non-zero exit, so wrap with `!`.
! python3 -m cpu_thermals --no-tui 2>"$TMP/err" \
    || fail "--no-tui without --csv should exit non-zero"
grep -q "requires --csv" "$TMP/err" \
    || fail "--no-tui error should mention 'requires --csv'"
ok "--no-tui without --csv is rejected with a clear message"

! python3 -m cpu_thermals --backend bogus 2>/dev/null \
    || fail "--backend bogus should exit non-zero"
ok "--backend rejects unknown values"

! python3 -m cpu_thermals not-a-number 2>/dev/null \
    || fail "non-numeric interval should exit non-zero"
ok "interval must be a number"

# Reject interval == 0 (would tight-loop) and negative intervals
# (would crash time.sleep). Both used to slip through `type=float`.
! python3 -m cpu_thermals 0 2>"$TMP/err" \
    || fail "interval 0 should exit non-zero"
grep -q "must be > 0" "$TMP/err" \
    || fail "interval 0 error should mention 'must be > 0'"
! python3 -m cpu_thermals -- -1.5 2>"$TMP/err" \
    || fail "negative interval should exit non-zero"
grep -q "must be > 0" "$TMP/err" \
    || fail "negative interval error should mention 'must be > 0'"
ok "interval must be strictly positive (rejects 0 and negatives)"


# ------------------------------------------------ CSV pipeline (fake backend)

section "CSV pipeline (fake backend)"

# --csv to a file
python3 tests/fake_run.py 0.001 --csv "$TMP/out.csv" --no-tui \
    >/dev/null 2>"$TMP/err"
# Note: csv.writer emits RFC 4180 CRLF line endings, so we strip \r
# before comparing the header line.
[[ "$(head -1 "$TMP/out.csv" | tr -d '\r')" == "timestamp,node,sensor,celsius" ]] \
    || fail "csv file should start with the header"
[[ "$(wc -l <"$TMP/out.csv")" -eq 7 ]] \
    || fail "csv file should be header + 3 reads * 2 sensors = 7 lines"
grep -q "wrote 6 rows" "$TMP/err" \
    || fail "stderr should report 'wrote 6 rows'"
ok "--csv FILE writes header + 6 rows + summary on stderr"

# Re-running appends without a duplicate header.
python3 tests/fake_run.py 0.001 --csv "$TMP/out.csv" --no-tui \
    >/dev/null 2>/dev/null
[[ "$(grep -c '^timestamp,' "$TMP/out.csv")" -eq 1 ]] \
    || fail "second run should not add a duplicate header"
[[ "$(wc -l <"$TMP/out.csv")" -eq 13 ]] \
    || fail "second run should leave header + 12 data rows"
ok "second --csv FILE run appends cleanly"

# --csv -  (stdout, TUI auto-suppressed)
python3 tests/fake_run.py 0.001 --csv - >"$TMP/out.csv" 2>"$TMP/err"
[[ "$(head -1 "$TMP/out.csv" | tr -d '\r')" == "timestamp,node,sensor,celsius" ]] \
    || fail "--csv - should write header to stdout"
grep -q "TUI suppressed" "$TMP/err" \
    || fail "stderr should warn about TUI auto-suppress"
grep -q "recording CSV to stdout" "$TMP/err" \
    || fail "stderr should have the recording banner"
ok "--csv - streams CSV to stdout, banner + auto-suppress note on stderr"

# --csv -  --no-tui  (explicit; no auto-suppress note)
python3 tests/fake_run.py 0.001 --csv - --no-tui >/dev/null 2>"$TMP/err"
! grep -q "TUI suppressed" "$TMP/err" \
    || fail "--no-tui should silence the auto-suppress note"
ok "explicit --no-tui silences the auto-suppress note"


# ----------------------------------------------------- example shell scripts

section "examples/ shell scripts"

# Glob all *.sh anywhere under examples/ so new scripts get covered
# automatically without having to update this file. (Avoids `mapfile`,
# which is bash 4+ -- macOS ships /bin/bash 3.2.)
example_scripts=()
while IFS= read -r s; do
    example_scripts+=("$s")
done < <(find examples -type f -name '*.sh' | sort)
[[ "${#example_scripts[@]}" -gt 0 ]] || fail "no shell scripts found under examples/"

for s in "${example_scripts[@]}"; do
    bash -n "$s" || fail "$s has a bash syntax error"
done
ok "${#example_scripts[@]} shell scripts pass bash -n"

if command -v shellcheck >/dev/null 2>&1; then
    for s in "${example_scripts[@]}"; do
        shellcheck "$s" || fail "shellcheck on $s"
    done
    ok "${#example_scripts[@]} shell scripts pass shellcheck"
else
    ok "shellcheck not installed (skipping)"
fi


# ------------------------------------------------ systemd unit + logrotate

section "examples/ systemd + logrotate"

UNIT="examples/3-systemd-csv-rotation/cpu-thermals.service"
# `Restart=on-failure` (rather than =always) so a logrotate-driven
# `systemctl restart` doesn't count as a failure against StartLimitBurst.
# Both StartLimit* directives bound noisy retry storms on broken hosts.
for required in '^\[Unit\]' '^\[Service\]' '^\[Install\]' \
                '^ExecStart=/usr/local/bin/cpu-thermals --csv -' \
                '^StandardOutput=append:' '^Restart=on-failure' \
                '^StartLimitBurst=' '^StartLimitIntervalSec='; do
    grep -qE "$required" "$UNIT" || fail "systemd unit missing: $required"
done
ok "systemd unit has required sections + critical keys (incl. restart guards)"

LR="examples/3-systemd-csv-rotation/cpu-thermals.logrotate"
[[ "$(tr -cd '{' <"$LR" | wc -c)" -eq "$(tr -cd '}' <"$LR" | wc -c)" ]] \
    || fail "logrotate config has unbalanced braces"
grep -q "postrotate" "$LR" || fail "logrotate config missing postrotate"
grep -q "endscript"  "$LR" || fail "logrotate config missing endscript"
ok "logrotate config is well-formed"


# ------------------------------------------------ apptainer .def files

section "examples/ apptainer .def files"

# Glob all *.def files anywhere under examples/ so new ones get covered
# automatically. We don't actually `apptainer build` -- Apptainer isn't
# installable on the default GitHub/GitLab Linux runners without
# significant setup, and that's out of proportion to the value. We do
# verify each .def has the required sections so it doesn't silently rot.
def_files=()
while IFS= read -r f; do
    def_files+=("$f")
done < <(find examples -type f -name '*.def' | sort)
[[ "${#def_files[@]}" -gt 0 ]] || fail "no .def files found under examples/"

for d in "${def_files[@]}"; do
    for required in '^Bootstrap:' '^From:' '^%post' '^%runscript'; do
        grep -qE "$required" "$d" || fail "$d missing section/header: $required"
    done
done
ok "${#def_files[@]} apptainer .def files have required headers + sections"


echo
echo "All checks passed."
