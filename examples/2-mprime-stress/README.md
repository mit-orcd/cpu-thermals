# Example 2 — mprime stress + CSV recording

A scripted CPU stress test: download `mprime` (Prime95), run a short torture test, and have `cpu-thermals` record temperatures to CSV in the background. On dual-socket Linux machines the script runs three phases — first one CPU, then the other, then both — each with all of that CPU's cores under load. On single-socket machines (laptops, Apple Silicon) it runs one combined phase. Default duration is 10 seconds per phase.

The output is two CSV files in a timestamped directory:

- `temps.csv`  — one row per sensor sample (long format from `cpu-thermals --csv`).
- `phases.csv` — one row per phase with start time, end time, and a status (`ok` if the phase completed cleanly or was killed by `timeout`; `FAILED:exit=N` otherwise).

Joining the two on timestamp lets any analysis tool answer "how hot did it get during the *socket-1* phase?" without ambiguity.

## What this shows

How to combine `cpu-thermals --csv` with a real, controlled CPU load and label the recording with phase boundaries so the resulting data is analysable. Demonstrates per-socket pinning via `taskset` on dual-socket Linux systems.

## Prerequisites

- `cpu-thermals` installed and on `PATH` (see [top-level README](../../README.md#install--run)).
- The platform-appropriate temperature tool (`lm-sensors` on Linux, `smctemp` on macOS).
- `bash`, `curl`, `tar`.
- `timeout` (Linux: ships in `coreutils`) **or** `gtimeout` (macOS: `brew install coreutils`).
- Linux dual-socket runs additionally need `taskset` (util-linux). It's almost always already there.
- Internet access for the first run (mprime download, ~10 MB). Subsequent runs reuse the cached `mprime/` directory.
- A few minutes on AC power. Stress tests heat the chip; let it cool between runs.

## How to run

From this directory:

```bash
./run.sh
```

Tweak via env vars:

```bash
DURATION=30   ./run.sh                                  # 30s per phase
SAMPLE_INTERVAL=1.0   ./run.sh                          # sample once a second
OUTPUT_DIR=/tmp/cool-test ./run.sh                      # explicit output dir
MPRIME_URL=https://...your-version.tar.gz ./run.sh      # newer mprime
MPRIME_DIR=$HOME/.cache/cpu-thermals-mprime ./run.sh    # writable cache outside the checkout
```

The script prints what it's doing as it goes and ends with the path to the results directory.

## What you should see

Console output (single-socket macOS example):

```
>> Detected: 1 socket(s), 8 logical CPU(s)
>> Starting cpu-thermals --csv ./results/20260418-114429/temps.csv --no-tui (interval 0.5s)
[cpu_thermals] recording CSV to ./results/20260418-114429/temps.csv
>> Phase 'all-cores' (10s): gtimeout 10 ./mprime/mprime -t -W ./mprime
>> Done. Results in: ./results/20260418-114429
    temps.csv  - one row per sensor sample
    phases.csv - one row per phase (join on timestamp)
[cpu_thermals] wrote 24 rows to ./results/20260418-114429/temps.csv
```

`results/20260418-114429/temps.csv` (snippet):

```csv
timestamp,node,sensor,celsius
2026-04-18T11:44:29-04:00,my-laptop,CPU,54.3
2026-04-18T11:44:29-04:00,my-laptop,GPU,45.2
...
2026-04-18T11:44:35-04:00,my-laptop,CPU,86.1
2026-04-18T11:44:35-04:00,my-laptop,GPU,49.0
```

`results/20260418-114429/phases.csv`:

```csv
phase,start_iso,end_iso,status
all-cores,2026-04-18T11:44:30-04:00,2026-04-18T11:44:40-04:00,ok
```

A dual-socket Linux machine would show three rows: `socket-0`, `socket-1`, `all-sockets`. The `status` column reads `ok` for a clean run or a normal `timeout` exit (124 / 137 / 143); on any other non-zero exit (bad `taskset` mask, missing exec bit, broken mprime, etc.) it reads `FAILED:exit=N` and the run.sh prints a loud `!! Phase 'X' FAILED` line on stderr so you don't accept a silent miss.

### Quick analysis snippets

Peak temperature across the whole run:

```bash
awk -F, 'NR>1 {print $4}' results/*/temps.csv | sort -n | tail -1
```

Peak temperature *during* a specific phase (in pandas):

```python
import pandas as pd
temps  = pd.read_csv("results/20260418-114429/temps.csv",  parse_dates=["timestamp"])
phases = pd.read_csv("results/20260418-114429/phases.csv", parse_dates=["start_iso","end_iso"])
for _, p in phases.iterrows():
    mask = temps.timestamp.between(p.start_iso, p.end_iso)
    print(p.phase, "peak =", temps.loc[mask, "celsius"].max(), "C")
```

## Caveats

- **Single-socket (most laptops, Apple Silicon)**: only the combined `all-cores` phase runs. The dual-socket dance requires both `Socket(s) >= 2` from `lscpu` and `taskset` to be available.
- **macOS**: no `taskset`, so the per-socket dance never fires (it would only matter on dual-socket Mac Pros anyway). `gtimeout` from coreutils is required (`brew install coreutils`).
- **mprime config quirks**: the script writes a minimal `local.txt` + `prime.txt` to make mprime run torture mode without prompts. Across mprime versions the exact required keys can drift; if your mprime hangs on a prompt, run it once interactively in `$MPRIME_DIR` (default `examples/2-mprime-stress/mprime/`) to seed the config, then re-run `./run.sh`. The default `mprime/` directory is `.gitignore`d so cached config is safe.
- **mprime downloads**: the default `MPRIME_URL` points at v30.19b20 on mersenne.org. If that 404s in the future, override `MPRIME_URL` with a current one from <https://www.mersenne.org/download/>. If the host has no internet, pre-place the `mprime` binary at `$MPRIME_DIR/mprime` (chmod +x) and the script will skip the download.
- **Read-only checkouts**: by default the script writes the downloaded mprime tree under the script directory. On read-only checkouts (CI, deployed clones, etc.) set `MPRIME_DIR=$HOME/.cache/cpu-thermals-mprime` (or any writable path) once and the script will reuse the cache thereafter. The script fails fast with an actionable error message if the chosen directory isn't writable.
- **Stress = heat**: laptops without active cooling (or with dust-clogged fans) can hit thermal throttle within seconds. That's actually useful information; just don't be surprised.

## What to look at next

- **[../1-simple-terminal/](../1-simple-terminal/)** for the live colored TUI without recording.
- **[../3-systemd-csv-rotation/](../3-systemd-csv-rotation/)** to capture temperatures *continuously* (instead of for a single test) and let analysis / alerting tools subscribe to the file.
