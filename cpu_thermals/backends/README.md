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
| `lm_sensors.py`    | Linux (Intel + AMD)   | `sensors` (lm-sensors) | Parses `Package id` (Intel) and `Tctl`/`Tccd` (AMD). |
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

## AMD Tctl vs Tccd (chiplet architectures)

AMD EPYC and Ryzen processors with chiplet architecture (Zen 2+) report two kinds of temperature through the `k10temp` kernel driver:

- **Tctl** ("Temperature Control") -- a synthetic value with an artificial offset (~27 C+) designed to drive fan curves aggressively. This is *not* a physical die temperature.
- **Tccd1--TccdN** -- actual physical temperatures of individual Core Complex Dies (CCDs).

On a dual-socket EPYC 7763, for example, Tctl reads 95--98 C while the real die temps are 42--47 C. Reporting Tctl to the user is misleading and causes false thermal alarms.

### `CPU_THERMALS_AMD_SENSOR` environment variable

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | If any Tccd readings exist in the k10temp block, report `max(Tccd)` per socket. Otherwise fall back to Tctl. |
| `tctl` | Always use Tctl (legacy behaviour, backwards-compatible). |
| `tccd` | Report every individual Tccd reading per socket. Labels: `CPU0:CCD1` ... `CPU0:CCD8`, `CPU1:CCD1` ... etc. |

When `auto` mode selects Tccd and `Tctl - max(Tccd) > 10 C`, a one-time note is printed to stderr explaining the discrepancy and mentioning the override.

### Affected AMD families

- **EPYC Rome** (Zen 2, Family 17h Model 30h+)
- **EPYC Milan** (Zen 3, Family 19h Model 01h)
- **EPYC Genoa** (Zen 4, Family 19h Model 10h+)
- **Ryzen 3000+** (desktop Zen 2+)

Older AMD parts (Family 15h/16h/early 17h) typically report only Tctl without Tccd lines; the `auto` mode falls back to Tctl on those.

### References

- https://www.kernel.org/doc/html/latest/hwmon/k10temp.html
- AMD PPR (Processor Programming Reference) for Family 19h -- documents Tctl offset
- Project test data: `reviews/test_on_systems/checking_sensors/node2100/`

## Diagnostics when sensors is missing

When `sensors` is not found on PATH, `check()` probes the kernel before printing advice:

1. **Scan `/sys/class/hwmon/hwmon*/name`** for `coretemp` or `k10temp`. If found, the kernel already has a CPU temperature driver loaded — the user just needs the `sensors` userspace tool (package install or Apptainer container).

2. **If no CPU driver is found**, read `/proc/cpuinfo` for `vendor_id` to suggest the correct `modprobe` command (`coretemp` for Intel, `k10temp` for AMD, both if unknown). The message explains that the kernel module must be loaded first.

3. **Fallback**: if neither sysfs nor cpuinfo are readable (non-Linux, unusual container, etc.), the static `INSTALL_HELP` message is shown unchanged.

Both `_HWMON_DIR` and `_CPUINFO_PATH` are module-level variables that tests can override to inject fake filesystem layouts (same pattern as `fake_run.py` overriding `cli.detect`). The Apptainer container suggestion appears in both cases: directly as an option when the driver is loaded, and after the modprobe step when it isn't.

## Handling lm-sensors stderr noise

- Both `read()` and `check()` capture `sensors`' stderr rather than letting it inherit our terminal. lm-sensors prints one `Can't get value of subfeature energyN_input: Kernel interface error` line per inaccessible RAPL energy domain (root-only since CVE-2020-8694) on every invocation, and on a many-thread server those lines used to scroll over the live TUI at refresh-rate. We don't parse those values, so the captured stderr is discarded on the success path and only surfaced when it actually matters: verbatim on a non-zero exit, and inside the diagnostic dump when the parser finds no recognised package readings.
