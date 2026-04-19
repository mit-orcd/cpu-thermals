"""Pure statistics functions for the cpu_thermals stats sub-command.

Everything here operates on plain Python data (a list of (datetime,
float) tuples per sensor). No I/O, no argparse, no terminal width
detection -- all of that is in the sibling __init__.py orchestration
layer. Easy to unit-test in isolation, easy to reuse from a notebook.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, median, pstdev
from typing import Sequence, Tuple


@dataclass
class Summary:
    """The reduction of one sensor's samples to its summary statistics.

    Field naming notes:
    - ``minimum`` / ``maximum`` (not ``min`` / ``max``) so we don't shadow
      the builtins inside this module.
    - ``stdev`` is *population* standard deviation (statistics.pstdev)
      because we're describing the data we have, not estimating an
      underlying population. See compute.summarize for the full rationale.
    - ``kurtosis`` is *excess* kurtosis (Fisher; normal distribution -> 0)
      using the biased moment estimator m4/m2**2 - 3. Returns NaN when
      undefined (n < 4 or zero variance).
    """

    sensor: str
    n: int
    minimum: float
    maximum: float
    mean: float
    median: float
    stdev: float
    kurtosis: float
    start: datetime
    end: datetime


def kurtosis(data: Sequence[float]) -> float:
    """Excess kurtosis (Fisher; normal distribution -> 0).

    Uses the biased moment estimator m4 / m2**2 - 3 (n in denominator,
    matching scipy.stats.kurtosis with default bias=True). Returns NaN
    when n < 4 or when the data is constant (m2 == 0).

    The two-pass implementation reuses the squared deviations to compute
    both the second and fourth central moments, so the heavy work is
    done once per call.
    """
    n = len(data)
    if n < 4:
        return float("nan")
    m = sum(data) / n
    diffs2 = [(x - m) ** 2 for x in data]
    m2 = sum(diffs2) / n
    if m2 == 0:
        return float("nan")
    m4 = sum(d * d for d in diffs2) / n   # (x-m)^4 = ((x-m)^2)^2
    return m4 / (m2 * m2) - 3.0


def summarize(
    sensor: str, samples: Sequence[Tuple[datetime, float]]
) -> Summary:
    """Reduce a sensor's (timestamp, celsius) samples to a Summary.

    Why population stdev (pstdev) rather than sample stdev (stdev)?
    A capture is a complete record of what the sensor read during the
    window -- we are not sampling from a wider population that we want
    to estimate the variance of. Using pstdev matches the descriptive
    intent ("how much did this sensor jiggle around its mean during this
    capture") and avoids the n-vs-(n-1) gotcha downstream readers don't
    care about. The README documents this explicitly.

    Raises ValueError on empty input -- the caller (stats/__init__.run)
    only calls this with non-empty groups, so this is a safety net not a
    user-facing path.
    """
    if not samples:
        raise ValueError(f"no samples for sensor {sensor!r}")
    times, values = zip(*samples)
    return Summary(
        sensor=sensor,
        n=len(values),
        minimum=min(values),
        maximum=max(values),
        mean=fmean(values),
        median=median(values),
        # pstdev requires n >= 1; we guard for n < 2 because a single
        # sample has no spread, and statistics.pstdev would still happily
        # return 0.0 -- but a printed "stdev=0.0" for n=1 is misleading.
        stdev=pstdev(values) if len(values) >= 2 else float("nan"),
        kurtosis=kurtosis(values),
        start=min(times),
        end=max(times),
    )
