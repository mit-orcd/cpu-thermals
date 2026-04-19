"""Live colored TUI table renderer.

Prints one header row at startup, then one row per sample with each
temperature colored by severity (green / yellow / red) and shown next to
an ASCII bar graph that scales linearly between
:data:`BAR_MIN_C` and :data:`BAR_MAX_C`.

The renderer writes the table to ``stdout`` so it shares the user's
terminal, and writes the Ctrl-C farewell to ``stderr`` so it never
contaminates anything piped into stdout.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Sequence

from ..backends import Reading

from .._text import supports_utf8

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

VALUE_WIDTH = 11
BAR_WIDTH = 20
BAR_MIN_C = 40
BAR_MAX_C = 100


# Pick the bar fill and degree marker once at import time. The defaults
# look right on a modern terminal; the ASCII fallback keeps the table
# legible (and not garbled) when stdout can't encode the block character.
# UTF-8 detection lives in cpu_thermals._text so the stats sub-package
# can reuse the same predicate without importing this whole TUI module.
if supports_utf8():
    _BAR_FILL = "\u2588"   # U+2588 FULL BLOCK
    _DEGREE = "\u00b0C"    # U+00B0 DEGREE SIGN + C
else:
    _BAR_FILL = "#"
    _DEGREE = " C"


def get_color(temp: float) -> str:
    """Pick the ANSI color escape for a given temperature."""
    if temp >= 90.0:
        return RED
    if temp >= 80.0:
        return YELLOW
    return GREEN


def draw_bar(
    temp: float,
    min_t: int = BAR_MIN_C,
    max_t: int = BAR_MAX_C,
    width: int = BAR_WIDTH,
) -> str:
    """Render a fixed-width bar for ``temp``, colored by severity.

    Uses U+2588 (full block) when stdout supports UTF-8, falls back to
    plain '#' otherwise. See :func:`_supports_utf8`.
    """
    t = max(min_t, min(temp, max_t))
    fraction = (t - min_t) / (max_t - min_t)
    filled_len = int(width * fraction)
    bar = _BAR_FILL * filled_len + "-" * (width - filled_len)
    return f"{get_color(temp)}{bar}{RESET}"


def _format_header(labels: Sequence[str]) -> str:
    cols = [f"{'TIME':<10}"]
    cols.extend(f"{label:<{VALUE_WIDTH}}" for label in labels)
    cols.extend(
        f"{label + ' BAR (' + str(BAR_MIN_C) + '-' + str(BAR_MAX_C) + 'C)':<{BAR_WIDTH}}"
        for label in labels
    )
    return " | ".join(cols)


def _format_row(readings: Sequence[Reading]) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    parts = [f"{now:<10}"]
    for r in readings:
        val = f"{r.celsius:>5.1f}{_DEGREE}"
        parts.append(f"{get_color(r.celsius)}{val:<{VALUE_WIDTH}}{RESET}")
    for r in readings:
        parts.append(draw_bar(r.celsius))
    return " | ".join(parts)


class TableRenderer:
    """Live colored bar-graph table written to stdout."""

    name = "table"

    def start(self, labels: Sequence[str]) -> None:
        header = _format_header(labels)
        print(header)
        print("-" * max(len(header), 60))

    def row(self, readings: Sequence[Reading]) -> None:
        sys.stdout.write(_format_row(readings) + "\n")
        sys.stdout.flush()

    def stop(self) -> None:
        sys.stderr.write("\nExiting...\n")
