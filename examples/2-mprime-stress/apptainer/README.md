# Apptainer (SIF) packaging — example 2 (mprime stress)

The same controlled mprime stress test as the bare-metal `../run.sh`, packaged as a single immutable [Apptainer](https://apptainer.org/) `.sif` file. mprime is **baked into the image at build time**, so the container works on offline / air-gapped compute nodes.

This `apptainer/` directory is a parallel sibling to `../run.sh`. Pick whichever path fits your environment; you do not need both.

## What this is for

- HPC / cluster nodes with no internet, no `pip`, no install permissions, but Apptainer available.
- Reproducible stress runs: the SIF baked from a given commit will produce identical mprime + cpu_thermals behaviour everywhere it runs.
- Distributing one file (`rsync mprime-stress.sif fleetnode:~`) instead of cloning a repo per node.

## What's bundled vs. what the host must provide

This example is built so the host needs the **bare minimum** — no userspace tools, no `lm-sensors` install, no `pip`, no `mprime` install. Everything the run needs lives inside the SIF.

**Bundled in the image** (no host install needed):

- `python3` and the `cpu_thermals` package.
- The lm-sensors userspace binary (`sensors`) and library (`libsensors`).
- `taskset` (from `util-linux`) for per-socket CPU pinning.
- `timeout` (from `coreutils`) for bounding each stress phase.
- `bash`, `curl`, `tar`.
- The `mprime` binary itself, baked into `/opt/stress/mprime/mprime` at build time.
- A `debian:12-slim` base layer (~75 MB). We use Debian rather than Alpine here because the prebuilt mprime is dynamically linked against glibc and won't run under Alpine's musl — see the rationale comment at the top of `mprime-stress.def`.

**Required from the host** (kernel side only):

1. **A Linux x86_64 kernel.** mprime ships only as a Linux x86_64 binary; arm64 hosts cannot run this image. (The bare-metal `../run.sh` lets you swap in a different stressor on arm64.)
2. **One hwmon driver module loaded** for your CPU (auto-loaded by `udev` on essentially every modern distro):
   - Intel CPUs → `coretemp`
   - AMD CPUs → `k10temp`
3. **Apptainer 1.x** (or legacy Singularity 3.x) on `PATH`.
4. **A few minutes on AC power.** Stress = heat.

That's it. Notably **not** required on the host: `lm-sensors`, `pip`, `python3`, `mprime`, or any of the `coreutils`/`util-linux` userspace.

### Verify your host is ready (no install required)

```bash
uname -m                                # must be x86_64
ls /sys/class/hwmon/
cat /sys/class/hwmon/hwmon*/name        # should include coretemp or k10temp
```

If `uname -m` reports `x86_64` and you see `coretemp` or `k10temp`, you're done. Proceed to Build.

### If no usable hwmon module is loaded

Same fix as example 1 — load the module yourself, no `lm-sensors` install needed on the host:

```bash
sudo modprobe coretemp        # Intel
sudo modprobe k10temp         # AMD
```

To make persistent, add the module name to `/etc/modules-load.d/cpu-thermals.conf`.

## Build

```bash
./build.sh
```

Internet is needed at build time only (to fetch the Debian base layer and the mprime tarball). Result: `mprime-stress.sif` (~80 MB; mostly the Debian base + mprime). Runtime is fully offline.

## Run

```bash
./run.sh                       # ~10s phase(s) using upstream defaults
DURATION=30 ./run.sh           # 30s per phase
SAMPLE_INTERVAL=1.0 ./run.sh   # cpu-thermals samples once a second
OUTPUT_DIR=/tmp/mytest ./run.sh
```

Env vars that the bare-metal `../run.sh` understands (`DURATION`, `SAMPLE_INTERVAL`, `OUTPUT_DIR`, `MPRIME_URL`) all work here — Apptainer forwards the host environment by default.

## Where the results land

Under `$PWD/results/<timestamp>/`, exactly as with the bare-metal run. Two files per run:

- `temps.csv`  — one row per sensor sample (long format from `cpu-thermals --csv`).
- `phases.csv` — one row per stress phase (`phase, start_iso, end_iso`).

These are written via Apptainer's auto-mounted `$PWD`, so they're plain files on the host. Move / archive / pandas them like any other CSV.

## Why a runtime shim exists

The upstream `../run.sh` writes mprime config files (`prime.txt`, `local.txt`) next to the mprime binary at runtime. SIFs are read-only, so `/opt/stress/mprime/` inside the image cannot be written to.

The `container-entry.sh` shim, baked into the image at `/opt/stress/container-entry.sh` and invoked by `%runscript`, copies the baked-in `/opt/stress` tree into a writable `mktemp -d` under `$PWD` and `exec`s the upstream `run.sh` from there. That's the only Apptainer-specific code in this directory; the bare-metal `run.sh` stays unchanged.

The temporary work directory is cleaned up on exit (via a `trap`); the `results/` directory it produced is left in place on the host.

## Per-socket pinning

The upstream `run.sh`'s socket-aware logic Just Works inside the container:

- `/proc/cpuinfo` is visible from the host (auto-mounted); `run.sh` parses it for socket topology.
- `taskset` (from Alpine's `util-linux` package) is bundled in the image.
- On 2+ socket Linux hosts you'll see `socket-0`, `socket-1`, `all-sockets` phases; on single-socket hosts you'll see one combined `all-cores` phase.

## Shipping the .sif to other machines

```bash
rsync -av mprime-stress.sif fleetnode:~/
ssh fleetnode 'cd /tmp && apptainer run ~/mprime-stress.sif'
ssh fleetnode 'ls /tmp/results/'
```

No build step, no internet, no `pip` required on the destination. Apptainer + lm-sensors-loaded host is all that's needed.

## Caveats

- **x86_64 only** (mprime is a glibc-linked Linux x86_64 binary). On arm64, use the bare-metal `../run.sh` with a different stressor (e.g. `stress-ng`).
- **Why Debian, not Alpine** (matches example 1's base): mprime is dynamically linked against glibc, so it cannot run inside an Alpine (musl) container. We use `debian:12-slim` as the smallest standard glibc base. There's a comment in the `.def` file explaining this so a future contributor doesn't "optimize" it back to Alpine.
- **Kernel modules can't be loaded from inside the container.** Apptainer is unprivileged and has no kernel-side access. If `/sys/class/hwmon/` shows no useful sensors, do the one-time `sudo modprobe <module>` on the host (see the "Verify" section above).
- **Runs as the invoking user.** No root needed at runtime. mprime is a CPU-bound userspace job and doesn't need any special permissions.
- **Stress is heat**: laptops without active cooling, or dust-clogged fans, can hit thermal-throttle within seconds. That's actually useful information; just don't be surprised.
- **Internet needed only at build time.** The mprime download URL is pinned in `mprime-stress.def`. If the upstream URL ever 404s, edit the def and rebuild.

### If you don't see any temperatures in the captured CSV

If no recognised hwmon module is loaded on the host, the cpu-thermals process inside the container will exit with `error: 'sensors' produced no recognised CPU package readings` (and dump the raw `sensors` output to the journal) — mprime will keep running, but the captured CSV will be empty. Run the `cat /sys/class/hwmon/hwmon*/name` check above; an unloaded `coretemp` / `k10temp` module is by far the most common cause.

## What to look at next

- **[../README.md](../README.md)** for the bare-metal harness (no container required).
- **[../../1-simple-terminal/apptainer/](../../1-simple-terminal/apptainer/)** for the simpler "just run cpu-thermals" image.
