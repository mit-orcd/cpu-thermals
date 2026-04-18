"""Append-safe CSV renderer (file or stdout).

Writes one row per sensor sample (long / tidy format) so that CSVs from
many machines can be concatenated and grouped without column-schema
gymnastics:

    timestamp,node,sensor,celsius
    2026-04-18T10:26:14-07:00,my-laptop,CPU,54.2
    2026-04-18T10:26:14-07:00,my-laptop,GPU,48.7

Conventions:

* Banner ("recording CSV to ...") and Ctrl-C summary go to ``stderr`` so
  they never end up inside the CSV file (or stdout pipe).
* In file mode the destination is opened in append mode and is line-
  buffered, so ``tail -f`` shows new readings as they arrive.
* In file mode the header is only written when the destination is new or
  empty, so re-using a path concatenates cleanly. In stdout mode every
  invocation is a fresh stream, so the header is always written.
* The sentinel path ``"-"`` means stdout (standard Unix idiom). The
  caller is expected to also suppress the TUI in that case.
"""

from __future__ import annotations

import csv
import os
import socket
import sys
from datetime import datetime
from typing import Sequence

from ..backends import Reading

HEADER = ("timestamp", "node", "sensor", "celsius")
STDOUT_SENTINEL = "-"


def default_csv_path() -> str:
    """Return ``cpu_thermals-<host>-<YYYYMMDD-HHMMSS>.csv`` in the CWD.

    The hostname is embedded so a file copied off a fleet node still
    identifies itself; the timestamp prevents accidentally clobbering a
    prior run.
    """
    host = socket.gethostname()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"cpu_thermals-{host}-{stamp}.csv"


class CsvRenderer:
    """Stream temperature readings to a CSV file or to stdout."""

    name = "csv"

    def __init__(self, path: str) -> None:
        self._path = os.fspath(path)
        self._is_stdout = self._path == STDOUT_SENTINEL
        self._owns_stream = not self._is_stdout
        self._node = socket.gethostname()
        self._rows = 0
        self._stream = None  # bound in start()
        self._writer = None

        # Validate the parent directory up front so a typo errors before
        # we go check the temperature tool, but defer the actual open to
        # start() so a failed source.check() doesn't leave an empty file
        # behind on disk. Stdout has no parent to validate.
        if not self._is_stdout:
            parent = os.path.dirname(self._path) or "."
            if not os.path.isdir(parent):
                raise SystemExit(f"error: directory does not exist: {parent}")

    def start(self, labels: Sequence[str]) -> None:
        # ``labels`` is intentionally unused: the schema is fixed so that
        # rows from heterogeneous backends concatenate cleanly downstream.
        del labels
        if self._is_stdout:
            self._stream = sys.stdout
            needs_header = True
            dest = "stdout"
        else:
            needs_header = (
                not os.path.exists(self._path)
                or os.path.getsize(self._path) == 0
            )
            try:
                self._stream = open(self._path, "a", newline="", buffering=1)
            except OSError as e:
                raise SystemExit(f"error: cannot open CSV file {self._path!r}: {e}")
            dest = self._path
        self._writer = csv.writer(self._stream)
        if needs_header:
            self._writer.writerow(HEADER)
            self._stream.flush()
        sys.stderr.write(f"[cpu_thermals] recording CSV to {dest}\n")

    def row(self, readings: Sequence[Reading]) -> None:
        assert self._writer is not None, "CsvRenderer.start() must be called first"
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            for r in readings:
                self._writer.writerow(
                    (ts, self._node, r.label, f"{r.celsius:.1f}")
                )
                self._rows += 1
            self._stream.flush()
        except BrokenPipeError:
            # Consumer closed the pipe (e.g. `cpu-thermals --csv - | head`).
            # Unwind via the existing KeyboardInterrupt path so the run loop
            # still calls renderer.stop() once and exits cleanly.
            raise KeyboardInterrupt

    def stop(self) -> None:
        if self._owns_stream and self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
        dest = "stdout" if self._is_stdout else self._path
        try:
            sys.stderr.write(
                f"[cpu_thermals] wrote {self._rows} rows to {dest}\n"
            )
        except BrokenPipeError:
            pass
