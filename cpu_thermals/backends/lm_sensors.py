"""Linux backend: reads CPU package temperatures via the ``sensors`` command.

Supports both Intel ``coretemp`` (``Package id``) and AMD ``k10temp`` (``Tctl``)
adapter blocks, which is what the original cpu_thermals.py targeted.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import List

from . import Reading


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
        # those values; only `Package id` (Intel) / `Tctl:` (AMD) on
        # stdout matter. Real failures (non-zero exit) still surface
        # both our message and the captured stderr verbatim.
        # `except OSError` (rather than the broader `except Exception`)
        # mirrors check() above and matches what subprocess.run actually
        # raises when the binary isn't executable; we don't want to
        # accidentally swallow a programming error here.
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

        temps: List[float] = []
        adapter_type = None

        for line in output.split("\n"):
            if "coretemp-isa" in line:
                adapter_type = "intel"
            elif "k10temp-pci" in line:
                adapter_type = "amd"

            elif adapter_type == "intel" and "Package id" in line:
                match = re.search(r"\+([0-9.]+)", line)
                if match:
                    temps.append(float(match.group(1)))

            elif adapter_type == "amd" and "Tctl:" in line:
                match = re.search(r"\+([0-9.]+)", line)
                if match:
                    temps.append(float(match.group(1)))

        if not temps:
            # Better to fail loudly than to return [0.0, 0.0] which can
            # look like a valid reading. Most likely cause: the host's
            # sensors output uses adapter / label names this parser
            # doesn't recognise yet (a chip beyond Intel coretemp + AMD
            # k10temp). Print both stdout and the captured stderr so the
            # user can file an issue or extend the parser. (Stderr is
            # captured rather than tee'd through to the terminal, see
            # the comment in read() above; we surface it here so a
            # genuinely-malformed parse still has full context.)
            sys.stderr.write(
                "error: 'sensors' produced no recognised CPU package "
                "readings.\n"
                "Currently supported adapters: coretemp-isa (Intel "
                "Package id), k10temp-pci (Tctl).\n"
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

        # Return whatever was parsed -- one reading on a single-package
        # system, two on a dual-package system, etc. The renderers handle
        # any column count; padding to a fixed width was the old
        # behaviour and produced misleading "0.0 C" entries.
        return [
            Reading(f"CPU{i}", temp)
            for i, temp in enumerate(temps)
        ]
