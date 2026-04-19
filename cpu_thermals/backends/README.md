# `cpu_thermals.backends` — temperature sources

Each module in this directory teaches the program how to read CPU temperatures on one platform. The shared interface is small enough to fit on a postcard:

```python
class TempSource(Protocol):
    name: str           # short id used by --backend
    install_help: str   # message shown when the underlying tool is missing
    def check(self) -> None: ...                # exit cleanly if unusable
    def read(self) -> Sequence[Reading]: ...    # one shot of readings
```

A `Reading` is just `(label: str, celsius: float)`.

## Current backends

| Module             | Platform              | Underlying tool        | Notes                                                |
| ------------------ | --------------------- | ---------------------- | ---------------------------------------------------- |
| `lm_sensors.py`    | Linux (Intel + AMD)   | `sensors` (lm-sensors) | Parses `Package id` (Intel) and `Tctl` (AMD).        |
| `smctemp.py`       | macOS Apple Silicon   | `smctemp` (third-party)| No sudo; CPU and GPU die temps via SMC keys.         |

Auto-selection lives in [`__init__.py`](__init__.py): the `_AUTO_BY_PLATFORM` table maps `platform.system()` to a backend name, and `detect()` picks one (or honours an explicit `--backend` choice).

## Adding a new backend

Drop a new file (say `mybackend.py`) here that defines a class with the four members above. Then register it in [`__init__.py`](__init__.py):

```python
def _make_mybackend() -> TempSource:
    from .mybackend import MyBackendSource
    return MyBackendSource()

_BACKENDS["mybackend"] = _make_mybackend          # exposes --backend mybackend
_AUTO_BY_PLATFORM["FreeBSD"] = "mybackend"        # optional auto-select rule
```

The lazy `from .mybackend import ...` keeps the import graph small: a Linux machine never imports the macOS backend, and vice versa. That's also why each backend's `INSTALL_HELP` string lives next to its implementation rather than in this `__init__`.

## Behaviour on unrecognised sensors output

`LmSensorsSource.read()` returns one `Reading` per CPU package it finds — labelled `CPU0`, `CPU1`, ... — by parsing the `coretemp-isa` (Intel) and `k10temp-pci` (AMD) blocks in `sensors` output. Implications:

- If the host has a CPU outside that set (e.g. a workstation chip behind a super-IO sensor like `nct6775`), the parser will find no matches and `read()` exits with an error that includes the raw `sensors` output, so the user can either file an issue or extend the regex set. This used to silently pad with `0.0°C` per channel — that was misleading (an empty parse looked like a valid sensor saying "freezing") and was removed.
- The renderers (`TableRenderer`, `CsvRenderer`) accept any number of readings per sample. A single-package system shows one column in the TUI and one row per sample in the CSV; dual-package shows two; future N-package CPUs would show N. No code changes needed in the renderer layer when a backend returns a different count.
- Both `read()` and `check()` capture `sensors`' stderr rather than letting it inherit our terminal. lm-sensors prints one `Can't get value of subfeature energyN_input: Kernel interface error` line per inaccessible RAPL energy domain (root-only since CVE-2020-8694) on every invocation, and on a many-thread server those lines used to scroll over the live TUI at refresh-rate. We don't parse those values, so the captured stderr is discarded on the success path and only surfaced when it actually matters: verbatim on a non-zero exit, and inside the diagnostic dump when the parser finds no recognised package readings.
