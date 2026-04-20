"""Linux backend: reads CPU package temperatures via the ``sensors`` command.

Supports both Intel ``coretemp`` (``Package id``) and AMD ``k10temp`` (``Tctl``
/ ``Tccd1``--``TccdN``) adapter blocks.

On AMD chiplet CPUs (Zen 2+), the k10temp driver reports a synthetic Tctl
value (~27 C above physical die temps) alongside per-CCD physical temps
(Tccd1--TccdN).  By default this backend prefers the physical Tccd readings;
the ``CPU_THERMALS_AMD_SENSOR`` env var controls the behaviour explicitly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from . import Reading

_TEMP_RE = re.compile(r"\+([0-9.]+)")


def _parse_temp(line: str) -> Optional[float]:
    """Extract the first +NNN.N temperature value from a sensors output line."""
    m = _TEMP_RE.search(line)
    return float(m.group(1)) if m else None


# -- AMD sensor mode (env var, validated at import time) ---------------------

# Validate once at import so a bad value is caught before any sensor work
# starts (fail-fast, matches the project's parse-time validation pattern).
_AMD_SENSOR_MODE = os.environ.get("CPU_THERMALS_AMD_SENSOR", "auto").lower()
# AMD's documented Tctl offset is ~27 C; 10 C is a conservative floor
# for the "this divergence looks like a synthetic offset" warning.
_TCTL_TCCD_WARN_THRESHOLD = 10.0  # celsius

if _AMD_SENSOR_MODE not in ("auto", "tctl", "tccd"):
    sys.stderr.write(
        f"error: CPU_THERMALS_AMD_SENSOR={_AMD_SENSOR_MODE!r} "
        "is not recognised.\nValid values: auto, tctl, tccd\n"
    )
    sys.exit(1)


INSTALL_HELP = """\
Error: 'sensors' command not found.

cpu_thermals depends on the lm-sensors package. Install it for your distro:

  Debian / Ubuntu:
    sudo apt install lm-sensors
    sudo sensors-detect

  Rocky Linux / RHEL / Fedora / AlmaLinux:
    sudo dnf install lm_sensors
    sudo sensors-detect

  Arch Linux:
    sudo pacman -S lm_sensors
    sudo sensors-detect

After installation, run 'sensors' to verify it works, then re-run cpu_thermals.
"""


class LmSensorsSource:
    name = "lm-sensors"
    install_help = INSTALL_HELP

    def __init__(self) -> None:
        self._warned_tctl = False  # one-shot gate for Tctl discrepancy note

    def check(self) -> None:
        if shutil.which("sensors") is None:
            sys.stderr.write(self.install_help)
            sys.exit(127)

        # stdout=PIPE, stderr=PIPE (rather than stderr=STDOUT) so a real
        # `sensors` startup failure can be reported verbatim, while the
        # routine RAPL "energy*_input: Kernel interface error" stderr
        # spam (root-only since CVE-2020-8694) stays out of the user's
        # terminal. Same shape as read() below.
        try:
            proc = subprocess.run(
                ["sensors"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as e:
            sys.stderr.write(f"Error invoking 'sensors': {e}\n")
            sys.exit(1)

        if proc.returncode != 0:
            sys.stderr.write(
                "Error: 'sensors' is installed but failed to run "
                f"(exit code {proc.returncode}).\n"
                "Try running 'sudo sensors-detect' to configure kernel modules.\n"
            )
            stderr_text = proc.stderr.decode("utf-8", errors="replace")
            if stderr_text:
                sys.stderr.write(f"sensors stderr:\n{stderr_text}")
            sys.exit(proc.returncode or 1)

    def read(self) -> List[Reading]:
        # Capture stderr (rather than letting it inherit our terminal) so
        # `sensors`' routine "Can't get value of subfeature energyN_input:
        # Kernel interface error" lines -- one per inaccessible RAPL
        # domain on every invocation, root-only since CVE-2020-8694 --
        # don't scroll over the live TUI at refresh-rate. We never parse
        # those values; only `Package id` (Intel) / `Tctl:` + `TccdN:`
        # (AMD) on stdout matter. Real failures (non-zero exit) still
        # surface both our message and the captured stderr verbatim.
        try:
            proc = subprocess.run(
                ["sensors"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as e:
            sys.stderr.write(f"Error running 'sensors': {e}\n")
            sys.exit(1)

        if proc.returncode != 0:
            stderr_text = proc.stderr.decode("utf-8", errors="replace")
            sys.stderr.write(
                f"Error running 'sensors' (exit {proc.returncode}):\n"
                f"{stderr_text}"
            )
            sys.exit(1)

        # `errors="replace"` on both streams: lm-sensors output is
        # nominally UTF-8 (the degree sign is U+00B0), but a
        # mis-localised host or future locale-related quirk shouldn't
        # crash the read loop with UnicodeDecodeError mid-capture.
        # Matches the same defensive pattern used by the TUI renderer.
        output = proc.stdout.decode("utf-8", errors="replace")
        stderr_text = proc.stderr.decode("utf-8", errors="replace")

        # Intel temps go straight into a flat list (unchanged path).
        intel_temps: List[float] = []

        # AMD blocks are collected per k10temp adapter, then resolved
        # via _resolve_amd_block() which applies the sensor mode logic.
        # Each block: {"tctl": float|None, "tccds": [(ccd_num, temp), ...]}
        amd_blocks: List[dict] = []
        current_amd: Optional[dict] = None
        adapter_type: Optional[str] = None

        for line in output.split("\n"):
            if "coretemp-isa" in line:
                adapter_type = "intel"
                current_amd = None
            elif "k10temp-pci" in line:
                adapter_type = "amd"
                current_amd = {"tctl": None, "tccds": []}
                amd_blocks.append(current_amd)

            elif adapter_type == "intel" and "Package id" in line:
                temp = _parse_temp(line)
                if temp is not None:
                    intel_temps.append(temp)

            elif adapter_type == "amd" and current_amd is not None:
                if "Tctl:" in line:
                    temp = _parse_temp(line)
                    if temp is not None:
                        current_amd["tctl"] = temp
                else:
                    tccd_match = re.match(r"\s*Tccd(\d+):", line)
                    if tccd_match:
                        temp = _parse_temp(line)
                        if temp is not None:
                            ccd_num = int(tccd_match.group(1))
                            current_amd["tccds"].append((ccd_num, temp))

        # Resolve AMD blocks into Reading objects.
        readings: List[Reading] = []

        for i, temp in enumerate(intel_temps):
            readings.append(Reading(f"CPU{i}", temp))

        for i, block in enumerate(amd_blocks):
            socket_idx = len(intel_temps) + i
            readings.extend(
                self._resolve_amd_block(socket_idx, block["tctl"], block["tccds"])
            )

        if not readings:
            # Better to fail loudly than to return [0.0, 0.0] which can
            # look like a valid reading. Most likely cause: the host's
            # sensors output uses adapter / label names this parser
            # doesn't recognise yet (a chip beyond Intel coretemp + AMD
            # k10temp). Print both stdout and the captured stderr so the
            # user can file an issue or extend the parser.
            sys.stderr.write(
                "error: 'sensors' produced no recognised CPU package "
                "readings.\n"
                "Currently supported adapters: coretemp-isa (Intel "
                "Package id), k10temp-pci (Tctl/Tccd).\n"
                "Raw `sensors` output for diagnosis:\n"
                "----- BEGIN sensors stdout -----\n"
                f"{output}"
                "----- END sensors stdout -----\n"
            )
            if stderr_text:
                sys.stderr.write(
                    "----- BEGIN sensors stderr -----\n"
                    f"{stderr_text}"
                    "----- END sensors stderr -----\n"
                )
            sys.exit(1)

        return readings

    def _resolve_amd_block(
        self,
        socket_idx: int,
        tctl: Optional[float],
        tccds: List[Tuple[int, float]],
    ) -> List[Reading]:
        """Resolve one k10temp block into Reading(s) based on sensor mode.

        Mode ``auto``: prefer max(Tccd) when Tccd lines exist, else Tctl.
        Mode ``tctl``: always Tctl.
        Mode ``tccd``: all individual Tccd readings.
        """
        if _AMD_SENSOR_MODE == "tctl":
            if tctl is not None:
                return [Reading(f"CPU{socket_idx}", tctl)]
            # No Tctl somehow; fall through to Tccd if available.
            if tccds:
                max_tccd = max(t for _, t in tccds)
                return [Reading(f"CPU{socket_idx}", max_tccd)]
            return []

        if _AMD_SENSOR_MODE == "tccd":
            if tccds:
                return [
                    Reading(f"CPU{socket_idx}:CCD{ccd}", temp)
                    for ccd, temp in tccds
                ]
            # No Tccd lines; fall back to Tctl.
            if tctl is not None:
                return [Reading(f"CPU{socket_idx}", tctl)]
            return []

        # auto mode: prefer Tccd when available.
        if tccds:
            max_tccd = max(t for _, t in tccds)
            self._maybe_warn_tctl(tctl, max_tccd)
            return [Reading(f"CPU{socket_idx}", max_tccd)]

        if tctl is not None:
            return [Reading(f"CPU{socket_idx}", tctl)]

        return []

    def _maybe_warn_tctl(
        self, tctl: Optional[float], max_tccd: float
    ) -> None:
        """One-time stderr note when Tctl diverges from physical Tccd temps."""
        if self._warned_tctl or tctl is None:
            return
        if tctl - max_tccd > _TCTL_TCCD_WARN_THRESHOLD:
            self._warned_tctl = True
            sys.stderr.write(
                f"note: AMD Tctl ({tctl:.1f}\u00b0C) is a fan-control "
                "value, not a physical\ntemperature. Reporting actual "
                f"die temp max(Tccd) = {max_tccd:.1f}\u00b0C instead.\n"
                "Override with CPU_THERMALS_AMD_SENSOR=tctl if needed.\n"
                "See: https://www.kernel.org/doc/html/latest/hwmon/"
                "k10temp.html\n"
            )
