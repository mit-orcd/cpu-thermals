"""Command-line interface for cpu_thermals.

Wires a temperature backend (see :mod:`cpu_thermals.backends`) to one or
more output renderers (see :mod:`cpu_thermals.output`) and runs the sample
loop. Almost all behaviour lives in those two subpackages; this module
deliberately stays thin so a reader can scan it top-to-bottom.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from typing import Optional, Sequence

from .backends import BACKEND_NAMES, TempSource, detect
from .output import Renderer, select
from .output.csv import default_csv_path

EPILOG = """\
Examples:
  cpu-thermals                       # live colored table, 2s refresh
  cpu-thermals 0.5                   # refresh twice a second
  cpu-thermals --csv                 # table + recording to auto-named .csv
  cpu-thermals --csv ~/cpu.csv       # table + recording to chosen file
  cpu-thermals --csv --no-tui        # silent capture (cron / SSH friendly)
  cpu-thermals --csv -               # CSV to stdout (TUI auto-suppressed)
  cpu-thermals --csv - | gzip >log.gz

Sub-commands:
  cpu-thermals stats CSVFILE         # per-sensor statistics from a recorded CSV
  cpu-thermals stats CSVFILE --plot  # also draw a Unicode sparkline per sensor
"""


# Sub-command names recognised by the dispatcher in main(). When argv[0]
# matches one of these, we delegate; otherwise we fall through to the
# legacy monitor parser, so `cpu-thermals 0.5 --csv -` keeps working
# unchanged. Adding a new sub-command means: add the name here, add a
# branch in _dispatch_subcommand below, ship a sub-package with a
# `run(argv) -> int` entry. See agents/AGENT_INSTRUCTIONS.md for the
# full recipe.
SUBCOMMANDS = frozenset({"stats"})


def run(source: TempSource, renderer: Renderer, interval: float) -> None:
    """Sample ``source`` every ``interval`` seconds and feed ``renderer``."""
    # Force SIGINT to raise KeyboardInterrupt even if our parent shell
    # backgrounded us with `&` (shells set SIG_IGN on background jobs;
    # without this, `kill -INT <pid>` from a long-running session would
    # be silently ignored).
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # Restore default SIGPIPE handling (Python normally translates SIGPIPE
    # into BrokenPipeError, which then leaks a noisy "Exception ignored"
    # message during interpreter shutdown when stdout is a closed pipe).
    # With SIG_DFL, `cpu-thermals --csv - | head` exits silently like any
    # other well-behaved Unix tool. Windows has no SIGPIPE.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    sample = source.read()
    renderer.start([r.label for r in sample])
    renderer.row(sample)
    try:
        while True:
            time.sleep(interval)
            renderer.row(source.read())
    except KeyboardInterrupt:
        renderer.stop()


def _positive_float(s: str) -> float:
    """argparse `type=` callable that requires a strictly positive float.

    Rejects negative values (which would make `time.sleep()` raise
    ValueError in the loop) and zero (which would peg a CPU in a tight
    loop). Both modes failed silently before; now they fail at parse
    time with a clear message.
    """
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid float value: {s!r}")
    if v <= 0:
        raise argparse.ArgumentTypeError(
            f"interval must be > 0 (got {v}); a small positive value like "
            "0.5 is fine, but 0 would tight-loop and negative would crash"
        )
    return v


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpu-thermals",
        description="Live CPU temperature monitor (Linux + macOS Apple Silicon).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "interval",
        nargs="?",
        type=_positive_float,
        default=2.0,
        help="Refresh interval in seconds, must be > 0 (default: 2.0)",
    )
    parser.add_argument(
        "--backend",
        choices=BACKEND_NAMES,
        default="auto",
        help="Temperature source. 'auto' picks one based on the current OS "
             "(Linux -> lm-sensors, Darwin -> smctemp).",
    )
    # ``--csv`` with no value uses the auto-generated path; ``--csv PATH``
    # uses an explicit path. Same shape as ``git diff --stat[=N]``.
    parser.add_argument(
        "--csv",
        nargs="?",
        const="<auto>",      # sentinel; resolved in main() so the default
        default=None,        # filename's timestamp matches start-of-run
        metavar="PATH",
        help=(
            "Also record CSV (timestamp,node,sensor,celsius). With no PATH, "
            "writes to cpu_thermals-<host>-<YYYYMMDD-HHMMSS>.csv in the "
            "current directory. Append-safe: re-using a path concatenates "
            "cleanly without duplicate headers. Use '-' for stdout "
            "(suppresses the TUI)."
        ),
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help=(
            "Suppress the live colored table. Requires --csv. Use for SSH, "
            "cron, or background captures where you only want the file."
        ),
    )
    return parser


def _resolve_csv_path(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value == "<auto>":
        return default_csv_path()
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by both ``python -m cpu_thermals`` and the console script.

    Dispatch shape: if argv[0] names a known sub-command (see
    SUBCOMMANDS above), hand the remaining args to that sub-command's
    ``run()``. Otherwise treat the whole argv as the legacy monitor
    invocation -- this keeps ``cpu-thermals 0.5 --csv -`` working
    exactly as it always has, without requiring users to re-learn a
    ``cpu-thermals monitor 0.5 --csv -`` shape.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SUBCOMMANDS:
        return _dispatch_subcommand(argv[0], argv[1:])
    return _monitor_main(argv)


def _dispatch_subcommand(name: str, sub_argv: Sequence[str]) -> int:
    """Look up the named sub-command and call its ``run(argv)`` entry.

    Imports are deliberately lazy so a plain ``cpu-thermals`` (monitor)
    invocation never pays the cost of importing a sub-command's
    transitive dependencies.
    """
    if name == "stats":
        from .stats import run as stats_run
        return stats_run(sub_argv)
    # Should be unreachable: SUBCOMMANDS is the source of truth.
    raise SystemExit(f"unknown subcommand: {name!r}")


def _monitor_main(argv: Sequence[str]) -> int:
    """The original cpu-thermals invocation: live monitor + optional CSV."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_path = _resolve_csv_path(args.csv)
    tui = not args.no_tui

    # CSV-to-stdout and the live TUI both want stdout, so they cannot
    # coexist. Auto-suppress the TUI (rather than erroring) so the obvious
    # one-liner Just Works; print a stderr note when we did so silently,
    # but stay quiet when the user already passed --no-tui.
    if csv_path == "-" and tui:
        tui = False
        sys.stderr.write(
            "[cpu_thermals] --csv -: TUI suppressed (stdout is the CSV)\n"
        )

    # Build the renderer first so a bad flag combo (e.g. --no-tui without
    # --csv, or an unwritable CSV directory) errors before we check for the
    # temperature tool. That keeps the user's first error message about
    # the thing they actually got wrong.
    renderer = select(tui=tui, csv_path=csv_path)

    source = detect(args.backend)
    source.check()

    run(source, renderer, args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
