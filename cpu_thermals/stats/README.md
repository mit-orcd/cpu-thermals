# `cpu_thermals.stats` — per-sensor statistics from a recorded CSV

The `cpu-thermals stats CSVFILE` sub-command reads a long-format CSV produced by `cpu-thermals --csv` and prints per-sensor descriptive statistics plus the capture window. With `--plot`, it appends a one-line Unicode (or ASCII) sparkline per sensor.

## What this is

A small post-processing utility for the CSVs cpu-thermals records. Designed for the common case: "I left a recording running, what did the temperatures look like?" Reads the CSV with stdlib `csv`, computes statistics with stdlib `statistics`, prints a fixed-width table — no third-party dependencies.

## Usage

```bash
cpu-thermals stats ./cpu_thermals-myhost-20260418-114429.csv
cpu-thermals stats ./out.csv --plot
cpu-thermals stats --help
```

## Output

Default (no `--plot`):

```
file:    /path/to/cpu_thermals-myhost-20260418-114429.csv
window:  2026-04-18T11:43:57-04:00  ->  2026-04-18T11:44:29-04:00   (32s)

sensor      n      min      max     mean   median    stdev     kurt
CPU         64     52.4     88.7     65.2     63.0      8.4    -0.70
GPU         64     43.8     51.2     46.5     46.1      2.1    -0.30
```

With `--plot`, a sparkline column is appended that consumes the remaining terminal width (auto-detected via `shutil.get_terminal_size`):

```
sensor      n      min      max     mean   median    stdev     kurt sparkline
CPU         64     52.4     88.7     65.2     63.0      8.4    -0.70 ▁▁▂▃▅▆▇█▇▅▃▂▁▂▃▅▆▇█▇▅▃▁
GPU         64     43.8     51.2     46.5     46.1      2.1    -0.30 ▂▃▄▅▆▇█▇▆▅▄▃▂▃▄▅▆▇█▇▆▄▃
```

`stdev` and `kurt` show `n/a` when undefined (`stdev` requires n ≥ 2; `kurt` requires n ≥ 4 and non-zero variance).

## Statistics chosen

- **min, max** — `min(values)` / `max(values)` (builtins). Trivial and unambiguous; included for completeness.
- **mean** — `statistics.fmean`. Faster than `statistics.mean` and equally precise for our purposes.
- **median** — `statistics.median`. Robust to a few outliers; useful for catching skewed distributions when read alongside `mean`.
- **stdev** — `statistics.pstdev` (**population** standard deviation, divisor `n`), not `statistics.stdev` (sample stdev, divisor `n-1`). A capture is a complete record of what the sensor read during the window; we are not estimating an underlying population. The choice matches the descriptive intent ("how much did this sensor jiggle around its mean during this capture?") and avoids the n-vs-(n-1) gotcha. If you want sample stdev, load the CSV in pandas and call `df.celsius.std()`.
- **kurt** — *excess* kurtosis (Fisher; normal distribution → 0) using the biased moment estimator `m4 / m2² − 3` (n in denominator). This matches `scipy.stats.kurtosis` with default `bias=True`, so a reader cross-checking with scipy/pandas gets the same number. Positive values mean heavier tails than normal (occasional spikes); negative values mean lighter tails (more uniform).

## `--plot` mode

Each sensor gets one line of `width` characters where `width` = remaining terminal columns (minimum 8). Each character is one of eight Unicode block-fill glyphs (U+2581 → U+2588) representing the sample's value relative to the sensor's own min/max range. The fallback predicate (`supports_utf8` in [`cpu_thermals/_text.py`](../_text.py)) is shared with the live TUI: it switches to an eight-step ASCII ramp `_.-=+*#@` whenever `sys.stdout.encoding` doesn't contain `utf` (typically `ascii` / `ANSI_X3.4-1968` / `latin-1` on locked-down `LANG=C` Linux setups, minimal server shells, and serial consoles). Note that on macOS even `LANG=C` usually leaves stdout encoding as `utf-8`, so the fallback won't trigger there — verify with `python3 -c "import sys; print(sys.stdout.encoding)"`.

If the sample count is greater than the available width, samples are downsampled by averaging contiguous bins (not by picking every Nth) so visual aliasing is minimised.

If all values are equal (zero range), the sparkline draws the lowest level throughout instead of dividing by zero.

## Edge cases

- **Missing file** → exit 1 with `error: cannot open CSV file ... no such file or directory`.
- **Empty CSV** (header only) → exit 1 with `error: no data rows in <path>`.
- **Wrong schema** (missing one of `timestamp` / `sensor` / `celsius`) → exit 1 with the columns we found, so the user can see what went wrong.
- **Single sample per sensor** → `stdev` and `kurt` print `n/a`; min == max == mean == median.
- **Constant data** → `stdev` = 0.0; `kurt` = `n/a` (zero variance).
- **CSV mixing nodes** → silently aggregated per sensor name. The `node` column is read but not currently grouped on; if you want per-node breakdown, pre-filter the CSV with `awk -F, -v n=NODE 'NR==1 || $2==n'` or use pandas.

## Adding a new statistic

The sub-package is intentionally split so that adding (say) p95 takes four small edits in known places:

1. Add a field to `Summary` in `compute.py`.
2. Compute it in `summarize()`.
3. Add a column header + format string entry to `_FIXED_COLS` in `__init__.py`, and a corresponding cell formatter in `_print_table()`.
4. Mention the new column in this README under "Statistics chosen".

Anything that doesn't fit into the table (e.g. a histogram) probably wants a new flag like `--histogram` rather than a column; the same four-step shape still applies (compute it, format it, document it, test it in `tests/smoke.sh`).

## What to look at next

- **[../../README.md](../../README.md)** — the live monitor, the CSV writer, and the integration story end to end.
- **[../output/README.md](../output/README.md)** — the TableRenderer / CsvRenderer pair on the recording side; the stats output borrows the same UTF-8 fallback approach.
- **[../backends/README.md](../backends/README.md)** — what produces the readings that end up in the CSV that this sub-command reads.
