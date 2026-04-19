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

        try:
            subprocess.check_output(["sensors"], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(
                "Error: 'sensors' is installed but failed to run "
                f"(exit code {e.returncode}).\n"
                "Try running 'sudo sensors-detect' to configure kernel modules.\n"
            )
            sys.exit(e.returncode or 1)
        except OSError as e:
            sys.stderr.write(f"Error invoking 'sensors': {e}\n")
            sys.exit(1)

    def read(self) -> List[Reading]:
        try:
            output = subprocess.check_output(["sensors"]).decode("utf-8")
        except Exception as e:
            sys.stderr.write(f"Error running 'sensors': {e}\n")
            sys.exit(1)

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
            # k10temp). Print the raw output so the user can file an
            # issue or extend the parser.
            sys.stderr.write(
                "error: 'sensors' produced no recognised CPU package "
                "readings.\n"
                "Currently supported adapters: coretemp-isa (Intel "
                "Package id), k10temp-pci (Tctl).\n"
                "Raw `sensors` output for diagnosis:\n"
                "----- BEGIN sensors output -----\n"
                f"{output}"
                "----- END sensors output -----\n"
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
