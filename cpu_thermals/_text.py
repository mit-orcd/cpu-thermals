"""Tiny terminal/text helpers shared between renderers.

Lives at the top of the package (not under ``output/`` or ``stats/``)
so a sub-package importing it doesn't accidentally pull in the live
TUI module. Currently exports one predicate:

* :func:`supports_utf8` -- best-effort check that ``sys.stdout`` can
  encode glyphs outside the ASCII range. Used by both the live TUI
  (block-fill bar + degree sign) and the stats sparkline.

Public via the underscore-free name so callers don't have to reach into
a private symbol.
"""

from __future__ import annotations

import sys


def supports_utf8() -> bool:
    """True if stdout looks like it can encode our default Unicode glyphs.

    Conservative: only treats utf-8/utf8 (any case) as supported.
    Falls back to ASCII otherwise. Matters for minimal server shells,
    serial consoles, and locked-down LANG=C / LC_ALL=C environments
    whose stdout encoding ends up as ``ascii``, ``ANSI_X3.4-1968``,
    ``latin-1``, etc.
    """
    enc = (sys.stdout.encoding or "").lower()
    return "utf" in enc
