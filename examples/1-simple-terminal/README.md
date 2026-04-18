# Example 1 — simple terminal run

A 30-second walkthrough of `cpu-thermals` running in your terminal with the live colored bar-graph display. No scripts, no setup beyond installing the tool. Start here if you've never used `cpu-thermals` before.

## What this shows

The default behavior of `cpu-thermals`: a refreshing two-column table of CPU temperatures with color-coded values and ASCII bar graphs that scale linearly between 40 °C and 100 °C.

## Prerequisites

- `cpu_thermals` installed (see the [top-level README](../../README.md#install--run)).
- The underlying temperature tool installed for your platform:
  - Linux: `lm-sensors` (`sudo apt install lm-sensors` / `sudo dnf install lm_sensors`).
  - macOS Apple Silicon: `smctemp` (`brew tap narugit/tap && brew install narugit/tap/smctemp`).
- A terminal with ANSI color support (basically any modern terminal).

## How to run

The default invocation:

```bash
cpu-thermals
```

A few useful variants:

```bash
cpu-thermals 0.5                 # refresh twice a second
cpu-thermals --csv               # also record CSV to an auto-named file in CWD
cpu-thermals --csv --no-tui      # silent capture (cron / SSH friendly)
cpu-thermals --csv -             # CSV to stdout, e.g. for piping
cpu-thermals --help              # all options + more examples
```

Press **Ctrl-C** to exit.

## What you should see

A header row, a separator, and one row per sample. With the bars below colored green/yellow/red by severity:

```
TIME       | CPU         | GPU         | CPU BAR (40-100C)    | GPU BAR (40-100C)
------------------------------------------------------------------------------------
11:34:33   |  55.4°C     |  46.2°C     | █████---------------- | ██------------------
11:34:35   |  54.8°C     |  46.2°C     | ████------------------ | ██------------------
11:34:37   |  55.0°C     |  46.1°C     | █████---------------- | ██------------------
```

(Column labels depend on your platform: Linux usually shows `CPU0` / `CPU1`; macOS Apple Silicon shows `CPU` / `GPU`.)

### Color legend

| Color  | Range          | Meaning                                  |
| ------ | -------------- | ---------------------------------------- |
| Green  | < 80 °C        | Comfortable.                             |
| Yellow | 80 – 90 °C     | Warm — under sustained load or heating.  |
| Red    | ≥ 90 °C        | Hot — close to thermal-throttle range.   |

### What `--csv` looks like

If you add `--csv`, you'll see the live table and a startup line on stderr telling you where the file went:

```
[cpu_thermals] recording CSV to cpu_thermals-myhost-20260418-114429.csv
```

Press Ctrl-C and you'll get a summary:

```
[cpu_thermals] wrote 8 rows to cpu_thermals-myhost-20260418-114429.csv
```

The CSV itself is long-format, one row per sensor:

```csv
timestamp,node,sensor,celsius
2026-04-18T11:44:29-04:00,myhost,CPU,54.3
2026-04-18T11:44:29-04:00,myhost,GPU,45.2
```

## What to look at next

- **[../3-systemd-csv-rotation/](../3-systemd-csv-rotation/)** — run cpu_thermals continuously as a systemd unit with log rotation, suitable as a feed for any analysis or alerting tool.
- **[../2-mprime-stress/](../2-mprime-stress/)** — drive a controlled CPU stress test (mprime) while recording, to see how the temperatures react to a known workload.
