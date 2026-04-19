# Apptainer (SIF) packaging — example 1

A self-contained [Apptainer](https://apptainer.org/) image that runs `cpu-thermals` from a single immutable `.sif` file. Aimed at HPC / shared-cluster environments where Docker isn't allowed but Apptainer (or its predecessor Singularity) is the standard way to ship software.

This `apptainer/` directory is a parallel sibling to the bare scripts (`watch.sh`, `watch-fast.sh`, etc.) one level up. Pick whichever path fits your environment; you do not need both.

## What this is for

- HPC compute nodes that have Apptainer but no `pip` / no internet / no install permissions.
- Shipping a known-good cpu_thermals build to a fleet by `rsync`-ing one file.
- Reproducible captures: the SIF baked from a given commit will produce the same CSV schema and behaviour everywhere it runs.

## What's bundled vs. what the host must provide

This example is built so the host needs the **bare minimum** — no userspace tools, no `lm-sensors` install, no `pip`. Everything cpu-thermals talks to lives inside the SIF.

**Bundled in the image** (no host install needed):

- `python3` and the `cpu_thermals` package.
- The lm-sensors userspace binary (`sensors`) and library (`libsensors`).
- An Alpine 3.19 base layer.

**Required from the host** (kernel side only):

1. **A Linux kernel.** Any recent version — hwmon has been in-tree since 2.6.x. No specific build options needed; every mainstream distro qualifies.
2. **One hwmon driver module loaded** for your CPU (auto-loaded by `udev` on essentially every modern distro):
   - Intel CPUs → `coretemp`
   - AMD CPUs → `k10temp`
3. **Apptainer 1.x** (or legacy Singularity 3.x) on `PATH`.

That's it. Notably **not** required on the host: `lm-sensors`, `pip`, `python3`, or `sensors-detect`.

### Verify your host is ready (no install required)

```bash
ls /sys/class/hwmon/
cat /sys/class/hwmon/hwmon*/name        # should include coretemp or k10temp
```

If the second command lists `coretemp` (Intel) or `k10temp` (AMD), you're done — proceed to Build.

### If no usable hwmon module is loaded

This is rare on modern distros, but if `/sys/class/hwmon/` is empty or only shows things like `acpitz` / `nvme`, load the right module yourself:

```bash
sudo modprobe coretemp        # Intel
sudo modprobe k10temp         # AMD
```

To make it persistent across reboots, add the module name to `/etc/modules-load.d/cpu-thermals.conf`. Still no `lm-sensors` install needed on the host.

## Build

```bash
./build.sh
```

Produces `cpu_thermals.sif` in this directory (around 40 MB; alpine + python3 + lm-sensors). The script `cd`s to the repo root before invoking `apptainer build` so the `%files` paths in `cpu_thermals.def` resolve cleanly without `../../../` ladders.

## Run

```bash
./run.sh                          # default 2-second TUI table
./run.sh 0.5                      # twice-per-second refresh
./run.sh --csv ~/cpu.csv          # also record CSV to a host-visible path
./run.sh --csv -                  # stream CSV to stdout (TUI auto-suppressed)
./run.sh --help                   # all flags
```

All `cpu-thermals` flags work because `%runscript` is `exec cpu-thermals "$@"`. Apptainer auto-mounts `$HOME`, `$PWD`, `/tmp`, and the host's `/sys`, so:

- CSV files written via `--csv PATH` land on the host filesystem (any path under `$HOME`, `$PWD`, or `/tmp`).
- `--csv` with no path drops `cpu_thermals-<host>-<ts>.csv` in `$PWD` on the host.
- `lm-sensors` reads the host's `/sys/class/hwmon/*` directly.

### Quick sanity check

```bash
./run.sh --csv - | head -5
```

Should print the header line plus 4 data rows then exit cleanly.

## Shipping the .sif to other machines

Just copy the file:

```bash
rsync -av cpu_thermals.sif fleetnode:~/
ssh fleetnode 'apptainer run cpu_thermals.sif --csv ~/cpu.csv'
```

No build step on the destination. No internet required at runtime. Works on any Linux host with Apptainer installed and lm-sensors loaded.

## Editing the image

The `.def` file is the source of truth. Common edits:

- **Different base image**: change `From: alpine:3.19` to e.g. `debian:12-slim`. Adjust the `apk add` line to `apt-get update && apt-get install -y` as appropriate.
- **Pin a specific cpu_thermals version**: instead of installing from the local source via `pip install .`, replace with `pip install cpu_thermals==X.Y.Z` from PyPI (when published).

## Caveats

- **Linux-only.** macOS users would need an Apptainer-aware Linux VM.
- **Architecture** matches whatever you build on (typically x86_64; arm64 builds work too — Alpine has an arm64 variant).
- **Kernel modules can't be loaded from inside the container.** Apptainer runs unprivileged and has no kernel-side access. If `/sys/class/hwmon/` shows no useful sensors on the host, you need a one-time `sudo modprobe <module>` on the host (see the "Verify your host is ready" section above).
- **Runs as the invoking user.** Apptainer doesn't need root and doesn't run as root by default. The container reads `/sys` as that user, which is fine because hwmon files are world-readable on every distro.

### If you don't see any temperatures

The container will exit with `error: 'sensors' produced no recognised CPU package readings` and dump the raw `sensors` output for diagnosis if no recognised hwmon module is loaded on the host. Run the two `ls` / `cat` commands in the "Verify" section above to confirm host readiness; an unloaded `coretemp` / `k10temp` module is by far the most common cause.

## What to look at next

- **[../../2-mprime-stress/apptainer/](../../2-mprime-stress/apptainer/)** for the mprime stress harness packaged the same way (and with mprime baked in so it works on offline nodes).
- **[../README.md](../README.md)** for the bare-metal scripts (no container required).
