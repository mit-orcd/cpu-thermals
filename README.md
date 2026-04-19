# cpu_thermals

A small CLI utility that displays live CPU temperatures with color-coded readings and ASCII bar graphs. Works on Linux (Intel `coretemp` and AMD `k10temp` via `lm-sensors`) and macOS Apple Silicon (via `smctemp`).

## Features

- Live, refreshing temperature readout for two channels (CPU/CPU on Linux, CPU/GPU on macOS)
- Color-coded output: green (< 80 °C), yellow (80–90 °C), red (≥ 90 °C)
- ASCII bar graph scaled from 40 °C to 100 °C
- Auto-detects the right backend for the current OS, with a `--backend` override
- `--csv` recording to a self-describing file (table stays on screen too)
- `--no-tui` for silent, headless capture (cron / SSH friendly)
- `cpu-thermals stats CSVFILE` post-processing sub-command for per-sensor min/max/mean/median/stdev/kurtosis (with optional `--plot` sparkline)
- Friendly startup check that tells you exactly how to install the missing tool per platform

## Requirements

- Python 3.8+ (standard library only — no runtime dependencies)
- A terminal with ANSI color support
- A platform-specific temperature tool (see below)

### Linux: install `lm-sensors`

Debian / Ubuntu:

```bash
sudo apt install lm-sensors
sudo sensors-detect
```

Rocky Linux / RHEL / Fedora / AlmaLinux:

```bash
sudo dnf install lm_sensors
sudo sensors-detect
```

Arch Linux:

```bash
sudo pacman -S lm_sensors
sudo sensors-detect
```

Verify:

```bash
sensors
```

### macOS (Apple Silicon): install `smctemp`

cpu_thermals uses [`smctemp`](https://github.com/narugit/smctemp) on macOS, which reads SMC sensor keys without requiring `sudo`. It is not in `homebrew-core`; install it from the maintainer's tap:

```bash
brew tap narugit/tap
brew install narugit/tap/smctemp
smctemp -c   # verify
```

Or build from source:

```bash
git clone https://github.com/narugit/smctemp.git
cd smctemp && sudo make install
```

Intel Macs are not currently supported (the chosen tool path targets Apple Silicon).

> Note: on M2 Macs, raw sensor values can be jittery; `smctemp` recommends `-i25 -n180 -f` for stable single-shot readings. cpu_thermals samples on its own interval, so this mostly affects manual `smctemp` invocations.

## Install / Run

You can use `cpu_thermals` either by running directly from a clone or by installing it with `pip`.

### Option 1: Run directly from the repo (no install)

```bash
git clone <this-repo> cpu_thermals
cd cpu_thermals
python3 -m cpu_thermals          # default 2-second refresh
python3 -m cpu_thermals 1        # refresh every 1 second
```

### Option 2: Install with pip

```bash
pip install .                    # from a local clone
# or
pip install git+<repo-url>       # straight from the repository
```

After install, the `cpu-thermals` command is available on your `PATH`:

```bash
cpu-thermals                     # default 2-second refresh
cpu-thermals 0.5                 # refresh every 0.5 seconds
cpu-thermals --help
```

### Choosing a backend

The active backend is auto-selected from the current OS, but you can force one:

```bash
cpu-thermals --backend lm-sensors    # force Linux backend
cpu-thermals --backend smctemp       # force macOS backend
cpu-thermals --backend auto          # default
```

This is useful for testing or running under unusual setups.

### Recording to CSV

`--csv` *adds* a CSV file destination without taking the live table away:

| Command                                | What happens                                                              |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `cpu-thermals`                         | Live colored table only. (Default.)                                       |
| `cpu-thermals --csv`                   | Live table **and** CSV recorded to an auto-named file in the CWD.         |
| `cpu-thermals --csv path/to/log.csv`   | Same, to your chosen path. Append-safe (no duplicate headers on re-runs). |
| `cpu-thermals --csv --no-tui`          | Silent capture: no table, just the CSV file. Cron / SSH friendly.         |
| `cpu-thermals --csv -`                 | CSV streamed to **stdout** for piping. TUI is auto-suppressed (stdout would clash) and a one-line stderr note tells you so; pass `--no-tui` to silence that note. |
| `cpu-thermals --no-tui`                | Rejected: there'd be nothing to do.                                       |

Pipe-friendly examples:

```bash
cpu-thermals --csv - | gzip > thermals.csv.gz       # compressed capture
cpu-thermals --csv - | head -20                     # quick sanity check
ssh fleetnode cpu-thermals --csv - >> all-nodes.csv # remote capture
```

The default filename is **`cpu_thermals-<hostname>-<YYYYMMDD-HHMMSS>.csv`** (for example `cpu_thermals-myhost-20260418-102614.csv`). The hostname makes the file self-identifying after it leaves the machine; the timestamp prevents accidentally clobbering a prior run.

The CSV uses a long / tidy schema so files from many machines concatenate cleanly:

```csv
timestamp,node,sensor,celsius
2026-04-18T10:26:14-07:00,my-laptop,CPU,54.2
2026-04-18T10:26:14-07:00,my-laptop,GPU,48.7
2026-04-18T10:26:16-07:00,my-laptop,CPU,55.1
2026-04-18T10:26:16-07:00,my-laptop,GPU,49.0
```

A startup banner (`[cpu_thermals] recording CSV to <path>`) and the final row-count summary are written to **stderr**, so they never end up inside the CSV file.

Press `Ctrl-C` to exit.

### Stats sub-command (`cpu-thermals stats CSVFILE`)

Once you have a recorded CSV, the `stats` sub-command produces per-sensor descriptive statistics plus the capture window:

```bash
cpu-thermals stats ./cpu_thermals-myhost-20260418-114429.csv
cpu-thermals stats ./out.csv --plot
```

Sample output:

```
file:    ./cpu_thermals-myhost-20260418-114429.csv
window:  2026-04-18T11:43:57-04:00  ->  2026-04-18T11:44:29-04:00   (32s)

sensor      n      min      max     mean   median    stdev     kurt
CPU         64     52.4     88.7     65.2     63.0      8.4    -0.70
GPU         64     43.8     51.2     46.5     46.1      2.1    -0.30
```

With `--plot`, a one-line Unicode sparkline is appended per sensor (ASCII fallback on non-UTF-8 terminals). `stdev` is **population** stdev (`statistics.pstdev`); `kurt` is **excess** kurtosis (Fisher; normal → 0) using the biased moment estimator that matches `scipy.stats.kurtosis` defaults. See [`cpu_thermals/stats/README.md`](cpu_thermals/stats/README.md) for the full output grammar, edge cases, and a recipe for adding new statistics.

### Exit codes

| Code | Meaning                                                                  |
| ---- | ------------------------------------------------------------------------ |
| `0`  | Clean exit (Ctrl-C from a normal session).                               |
| `1`  | Runtime error (sensor read failed, CSV path unwritable, OS unsupported). |
| `2`  | Invalid command-line arguments (argparse default).                       |
| `127`| Required tool (`sensors` or `smctemp`) is not installed.                 |

## Example output

Linux:

```
TIME       | CPU0        | CPU1        | CPU0 BAR (40-100C)   | CPU1 BAR (40-100C)
-------------------------------------------------------------------------------------
10:26:14   |  62.0°C     |  64.0°C     | ███████-------------  | ███████-------------
```

macOS (Apple Silicon):

```
TIME       | CPU         | GPU         | CPU BAR (40-100C)    | GPU BAR (40-100C)
-------------------------------------------------------------------------------------
10:26:14   |  54.2°C     |  48.7°C     | █████---------------  | ███-----------------
```

## Project layout

```
cpu_thermals/
├── cpu_thermals/
│   ├── __init__.py
│   ├── __main__.py          # enables `python -m cpu_thermals`
│   ├── cli.py               # arg parsing + main loop (deliberately thin)
│   ├── backends/            # WHERE temps come from -- one file per platform
│   │   ├── README.md        # how a backend works, how to add one
│   │   ├── __init__.py      # TempSource protocol + auto-detect dispatcher
│   │   ├── lm_sensors.py    # Linux (Intel coretemp + AMD k10temp)
│   │   └── smctemp.py       # macOS Apple Silicon
│   └── output/              # WHERE temps go -- one file per format
│       ├── README.md        # how a renderer works, how to add one
│       ├── __init__.py      # Renderer protocol + MultiRenderer + select()
│       ├── table.py         # live colored TUI table
│       └── csv.py           # append-safe CSV writer
├── pyproject.toml           # package metadata, console script entry point
├── README.md
└── .gitignore
```

The package has two clean axes: **backends** (where temperatures come from) and **output** renderers (where they go). [`cpu_thermals/backends/README.md`](cpu_thermals/backends/README.md) and [`cpu_thermals/output/README.md`](cpu_thermals/output/README.md) walk through each in detail and show 10-line recipes for adding a new one.

## Notes

- On startup the script verifies the underlying tool (`sensors` or `smctemp`) is installed and runnable. If not, it prints a per-platform install hint and exits with code `127`.
- The TUI display shows one column per sensor reading the active backend produces (one per CPU package on Linux, CPU + GPU on macOS Apple Silicon). If the lm-sensors backend can't recognise any sensor blocks in `sensors` output, it exits with a clear error and includes the raw `sensors` stdout *and* captured stderr for diagnosis (rather than silently emitting fake `0.0°C` readings). See [`cpu_thermals/backends/README.md`](cpu_thermals/backends/README.md) for the parser's coverage and how to extend it.

## License

MIT
