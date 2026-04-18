# cpu_thermals examples

Three self-contained recipes showing common ways to use `cpu_thermals`. Each lives in its own subdirectory with its own README; you can read them in any order, but the suggested order below works well for someone new to the tool.

## What's here

- **[1-simple-terminal/](1-simple-terminal/)** — Run `cpu-thermals` in a terminal and watch live colored bars. Just a README; no scripts. Start here.
- **[3-systemd-csv-rotation/](3-systemd-csv-rotation/)** — Run `cpu-thermals --csv -` continuously as a `systemd` unit on a Linux host, with `logrotate` keeping the captured CSV bounded. Suitable as a feed for any analysis or alerting tool that can read CSV. Includes an *optional* Ansible fragment for fleet deployment.
- **[2-mprime-stress/](2-mprime-stress/)** — A scripted stress-test harness: download `mprime`, run a torture test (per-CPU on dual-socket systems, single phase on single-socket), and record temperatures with `cpu-thermals --csv` in the background. Produces a `temps.csv` plus a `phases.csv` of labeled phase boundaries so analysis tools can correlate temps with the workload.

## Suggested reading order

1. **`1-simple-terminal/`** — see what cpu_thermals actually does.
2. **`3-systemd-csv-rotation/`** — see how to run it in production.
3. **`2-mprime-stress/`** — reproduce a controlled load to validate sensor coverage and thermal behavior.

## Adding more examples

The directory is open-ended. Each subdirectory follows the same README template (`What this shows` / `Prerequisites` / `How to run` / `What you should see` / `What to look at next`); copy any of them as a starting point.
