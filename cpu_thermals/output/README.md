# `cpu_thermals.output` — output renderers

Where the readings *go*. Backends decide what to read; renderers decide how to present it. The shared interface is three small methods:

```python
class Renderer(Protocol):
    name: str
    def start(self, labels: Sequence[str]) -> None: ...   # once, before first row
    def row(self, readings: Sequence[Reading]) -> None: ... # once per sample
    def stop(self) -> None: ...                           # once, on Ctrl-C
```

## Current renderers

| Module      | Destination                  | Notes                                                                |
| ----------- | ---------------------------- | -------------------------------------------------------------------- |
| `table.py`  | stdout (live colored TUI)    | Coloured bars, ASCII chrome. Uses U+2588 / U+00B0 on UTF-8 terminals; falls back to plain `#` and ` C` when `sys.stdout.encoding` doesn't look UTF-8 (minimal server shells, serial consoles, `LANG=C`). Farewell on Ctrl-C goes to **stderr**.  |
| `csv.py`    | a CSV file, or stdout (`-`)  | Long-format `(timestamp, node, sensor, celsius)`. Append-safe in file mode; always writes the header in stdout mode (every invocation is a fresh stream). Treats `BrokenPipeError` as a clean shutdown so `... --csv - \| head` doesn't traceback. |

## Composite: running both at once

`__init__.py` ships a tiny `MultiRenderer` that fans `start/row/stop` out to several children. `select(tui=..., csv_path=...)` builds the right combination:

* `tui=True`, `csv_path=None`            → just the table.
* `tui=False`, `csv_path="x.csv"`        → just the CSV.
* `tui=True`, `csv_path="x.csv"`         → both, wrapped in `MultiRenderer`.
* `tui=False`, `csv_path=None`           → refused (would do nothing).

The run loop in [`cpu_thermals.cli`](../cli.py) is therefore unaware of how many destinations are in play.

## Adding a new renderer

1. Add a module here (e.g. `json_lines.py`) with a class that implements the three methods above.
2. Wire it into `select()` in [`__init__.py`](__init__.py) — usually one new flag in the CLI plus one new branch here.

```python
# Sketch: a JSON-lines renderer in 10 lines.
import json, sys
from datetime import datetime
from ..backends import Reading

class JsonLinesRenderer:
    name = "jsonl"
    def __init__(self, stream=sys.stdout):
        self._stream = stream
    def start(self, labels): pass
    def row(self, readings):
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        for r in readings:
            self._stream.write(json.dumps({"t": ts, "sensor": r.label, "c": r.celsius}) + "\n")
        self._stream.flush()
    def stop(self): pass
```

## Conventions

* **Stdout is for the user-facing output**; status banners, error messages, and Ctrl-C summaries go to **stderr** so they never contaminate piped/recorded data.
* **Flush after every row** when writing to a file or pipe, otherwise `tail -f` looks broken because the OS buffers ~4 KB.
* **Header rows are written once**, in `start()`, never inside `row()`.
