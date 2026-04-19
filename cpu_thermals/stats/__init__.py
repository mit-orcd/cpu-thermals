"""``cpu-thermals stats CSVFILE`` -- per-sensor statistics from a recorded CSV.

This module is the orchestration layer for the stats sub-command. The
flow is:

    parse argv  ->  read CSV  ->  group rows by sensor  ->
    summarize each group (compute.summarize)  ->
    print a fixed-width table (+ optional sparkline column via plot)

Pure statistics functions live in compute.py; sparkline rendering lives
in plot.py. Everything I/O-shaped (argparse, file open, terminal width,
stdout writes) lives here so the other two modules stay easy to unit-
test in isolation.

CSV schema expected (the long-format produced by ``cpu-thermals --csv``):

    timestamp,node,sensor,celsius
    2026-04-18T11:43:57-04:00,my-laptop,CPU,54.2
    2026-04-18T11:43:57-04:00,my-laptop,GPU,44.0
    ...

The ``node`` column is read but not currently grouped on -- if a CSV
mixes hosts, all readings for the same sensor name are aggregated. The
README documents this and points at ``awk`` / pandas pre-filtering.
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

from .compute import Summary, summarize
from .plot import render_sparkline


# What the CSV reader requires. ``node`` is read when present but is
# not required (older recordings or hand-written CSVs may omit it),
# and isn't grouped on either way. Documented in stats/README.md.
_REQUIRED_COLUMNS = {"timestamp", "sensor", "celsius"}


# --------------------------------------------------------------- argparse

_STATS_EPILOG = """\
Examples:
  # Capture, then analyse:
  cpu-thermals --csv ./run.csv --no-tui     (Ctrl-C to stop)
  cpu-thermals stats ./run.csv
  cpu-thermals stats ./run.csv --plot

Column legend:
  stdev   population standard deviation (statistics.pstdev)
  kurt    excess kurtosis (Fisher; normal -> 0)
  n/a     statistic undefined for the data (e.g. stdev needs n>=2)
"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cpu-thermals stats",
        description="Per-sensor statistics from a cpu-thermals --csv recording.",
        epilog=_STATS_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "csvfile",
        help="path to a long-format CSV (required cols: timestamp, sensor, "
             "celsius; node is optional)",
    )
    p.add_argument(
        "--plot",
        action="store_true",
        help="append a Unicode sparkline column per sensor "
             "(ASCII fallback on non-UTF-8 terminals)",
    )
    return p


# --------------------------------------------------------------- timestamp parsing

def _parse_iso_ts(s: str) -> datetime:
    """Parse an ISO 8601 timestamp with optional timezone offset.

    Python 3.11+ ``datetime.fromisoformat`` handles the full grammar
    including offsets like ``-04:00`` and ``Z``. Earlier supported
    versions (3.8-3.10) only accept naive datetimes via ``fromisoformat``,
    so we fall back to ``strptime`` with ``%z`` (which has accepted
    both ``+0400`` and ``+04:00`` since 3.7).
    """
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


# --------------------------------------------------------------- CSV reader

def _read_csv(
    path: str,
) -> Dict[str, List[Tuple[datetime, float]]]:
    """Read a long-format CSV into {sensor: [(timestamp, celsius), ...]}.

    Validates schema (the three required columns must be present), exits
    on common user errors with a clear message rather than dumping a
    Python traceback.
    """
    try:
        f = open(path, newline="")
    except OSError as e:
        sys.stderr.write(f"error: cannot open CSV file {path!r}: {e}\n")
        sys.exit(1)

    by_sensor: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    with f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not _REQUIRED_COLUMNS.issubset(reader.fieldnames):
            sys.stderr.write(
                "error: required CSV columns missing.\n"
                "       Required: timestamp, sensor, celsius "
                "(node is optional and ignored if present).\n"
                f"       Got: {list(reader.fieldnames or [])}\n"
            )
            sys.exit(1)
        for row in reader:
            try:
                ts = _parse_iso_ts(row["timestamp"])
                value = float(row["celsius"])
            except (KeyError, ValueError) as e:
                sys.stderr.write(
                    f"error: malformed row in {path!r}: {row} ({e})\n"
                )
                sys.exit(1)
            # Reject non-finite values at parse time so the printer's
            # "n/a" path stays reserved for legitimately-undefined stats
            # (n<2 stdev, n<4 or zero-variance kurtosis). A literal
            # "nan"/"inf" in a temperature column is almost certainly a
            # broken upstream recording and should not be silently
            # propagated through min/max/mean.
            if not math.isfinite(value):
                sys.stderr.write(
                    f"error: non-finite celsius value in {path!r}: {row}\n"
                )
                sys.exit(1)
            by_sensor[row["sensor"]].append((ts, value))

    if not by_sensor:
        sys.stderr.write(f"error: no data rows in {path}\n")
        sys.exit(1)

    return by_sensor


# --------------------------------------------------------------- formatting

# Column widths chosen to keep the default invocation comfortably under
# 80 columns even with a sparkline column appended. `sensor` width grows
# at runtime for longer sensor names; the others are fixed.
_FIXED_COLS = (
    ("n",      6, "{:>6d}"),
    ("min",    8, "{:>8.1f}"),
    ("max",    8, "{:>8.1f}"),
    ("mean",   8, "{:>8.1f}"),
    ("median", 8, "{:>8.1f}"),
    ("stdev",  8, "{:>8}"),
    ("kurt",   8, "{:>8}"),
)


def _fmt_optional_float(v: float, fmt: str = "{:>7.2f}") -> str:
    """Format a float that might be NaN as either a number or `n/a`."""
    if v != v:                       # NaN check; NaN is the only value != itself
        return "n/a"
    return fmt.format(v)


def _terminal_width(default: int = 80) -> int:
    """Best-effort terminal width; sane default when stdout isn't a TTY."""
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except OSError:
        return default


def _print_table(
    summaries: Sequence[Summary],
    by_sensor: Dict[str, List[Tuple[datetime, float]]],
    csv_path: str,
    plot: bool,
    out=sys.stdout,
) -> None:
    """Render the stats table (header + per-sensor rows + optional sparkline)."""
    # Capture-window header. If different sensors have different time
    # ranges (rare but possible if the CSV is stitched together) we show
    # the overall window and let the per-row stats expose the rest.
    starts = [s.start for s in summaries]
    ends = [s.end for s in summaries]
    window_start = min(starts).isoformat(timespec="seconds")
    window_end = max(ends).isoformat(timespec="seconds")
    duration_s = int((max(ends) - min(starts)).total_seconds())

    out.write(f"file:    {csv_path}\n")
    out.write(
        f"window:  {window_start}  ->  {window_end}   ({duration_s}s)\n\n"
    )

    sensor_w = max(6, *(len(s.sensor) for s in summaries))
    headers = ["sensor".ljust(sensor_w)] + [
        h.rjust(w) for (h, w, _) in _FIXED_COLS
    ]
    if plot:
        headers.append("sparkline")
    out.write(" ".join(headers) + "\n")

    # Sparkline width = remaining terminal columns after the fixed cols.
    fixed_total = sensor_w + 1 + sum(w + 1 for (_, w, _) in _FIXED_COLS)
    spark_width = max(8, _terminal_width() - fixed_total)

    for s in summaries:
        cells = [s.sensor.ljust(sensor_w)]
        cells.append("{:>6d}".format(s.n))
        cells.append("{:>8.1f}".format(s.minimum))
        cells.append("{:>8.1f}".format(s.maximum))
        cells.append("{:>8.1f}".format(s.mean))
        cells.append("{:>8.1f}".format(s.median))
        cells.append("{:>8}".format(_fmt_optional_float(s.stdev, "{:.1f}")))
        cells.append("{:>8}".format(_fmt_optional_float(s.kurtosis, "{:.2f}")))
        if plot:
            values = [v for (_, v) in by_sensor[s.sensor]]
            cells.append(render_sparkline(values, width=spark_width))
        out.write(" ".join(cells) + "\n")


# --------------------------------------------------------------- public entry

def run(argv: Sequence[str]) -> int:
    """Sub-command entry; called by cpu_thermals.cli when argv[0] == 'stats'."""
    args = _build_parser().parse_args(list(argv))

    by_sensor = _read_csv(args.csvfile)
    summaries = [
        summarize(sensor, samples)
        for sensor, samples in sorted(by_sensor.items())
    ]
    _print_table(summaries, by_sensor, args.csvfile, plot=args.plot)
    return 0
