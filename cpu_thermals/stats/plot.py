"""One-line Unicode (or ASCII) sparkline rendering for cpu_thermals stats.

A sparkline is a one-character-per-sample visualisation of a series's
shape. We use the eight Unicode block-fill glyphs U+2581..U+2588 by
default; on terminals whose stdout encoding doesn't look UTF-8 we fall
back to a hand-picked eight-character ASCII ramp so the output stays
legible on minimal server shells, serial consoles, and `LANG=C`
environments.

UTF-8 detection is shared with the live TUI via the neutral
:mod:`cpu_thermals._text` helper -- importing it directly here keeps the
stats sub-package's import graph clean (no transitive pull of the TUI
renderer) while preserving "one predicate, one source of truth".
"""

from __future__ import annotations

from typing import Sequence

from .._text import supports_utf8

# Eight levels, light to dense. The Unicode glyphs are the standard
# sparkline ramp used by `spark`, asciichartpy, etc. The ASCII fallback
# is a hand-picked eight-step ramp of increasing visual weight.
_SPARKLINE_UTF8 = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARKLINE_ASCII = "_.-=+*#@"


def render_sparkline(values: Sequence[float], width: int = 40) -> str:
    """Render values as a one-line sparkline of at most ``width`` chars.

    - If len(values) > width, downsample by averaging contiguous bins so
      every output character represents roughly the same amount of input
      time. (Picking every Nth sample would be cheaper but would alias
      ugly on data that the eye can detect; binning is honest.)
    - If all values are equal (zero range), return the lowest level
      throughout instead of dividing by zero.
    - Empty input returns an empty string -- the caller decides whether
      that's an error or just "skip the sparkline column".
    """
    if not values:
        return ""
    glyphs = _SPARKLINE_UTF8 if supports_utf8() else _SPARKLINE_ASCII

    if len(values) > width:
        # Average values into `width` contiguous bins. step is fractional;
        # the int() casts give us the half-open [start, end) bin bounds.
        step = len(values) / width
        bins = []
        for i in range(width):
            start = int(i * step)
            end = int((i + 1) * step)
            # max(1, ...) guards the rare case where a tiny step lands
            # both bounds on the same index, which would divide by zero.
            n = max(1, end - start)
            bins.append(sum(values[start:end]) / n)
    else:
        bins = list(values)

    lo = min(bins)
    hi = max(bins)
    span = hi - lo
    if span == 0:
        return glyphs[0] * len(bins)
    last = len(glyphs) - 1
    return "".join(glyphs[round((b - lo) / span * last)] for b in bins)
