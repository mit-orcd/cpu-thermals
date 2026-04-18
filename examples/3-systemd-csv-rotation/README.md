# Example 3 — systemd + logrotate (continuous CSV capture)

A production-shaped recipe for capturing CPU temperatures continuously on a Linux host. Uses `cpu-thermals --csv -` to stream long-format CSV to stdout, lets `systemd` append it to `/var/log/cpu_thermals/cpu_thermals.csv`, and uses `logrotate` to keep the file bounded. The result is a self-describing CSV that any analysis or alerting tool (Datadog Agent, Telegraf, custom Python, an `awk` cron job) can ingest.

The bare files in this directory are the recommended single-host path. For fleet deployment, see the optional [`ansible/`](ansible/) fragment further down — it's a parallel sibling, completely ignorable if you don't use Ansible.

## What this shows

- How to run `cpu-thermals --csv -` continuously as a systemd unit.
- How to use `systemd`'s `StandardOutput=append:` to capture stdout to a log file with no shell pipe in the unit.
- How to wire `logrotate` so each daily archive starts with a CSV header (by restarting the service on rotation).
- How to keep the human-readable banner / summary lines out of the CSV file (they go to the journal via `StandardError=journal`).

## Prerequisites

- Linux with `systemd` 240+ (for `StandardOutput=append:`). Check with `systemctl --version`.
- `logrotate` installed and on its usual cron / systemd-timer schedule.
- `cpu_thermals` installed and on `PATH` as `/usr/local/bin/cpu-thermals` (or edit the `ExecStart=` line of the unit). See [top-level README](../../README.md#install--run).
- `lm-sensors` configured (`sudo sensors-detect`).
- Root or `sudo` for the install.

## Files

| File | Where it goes | Purpose |
| ---- | ------------- | ------- |
| `cpu-thermals.service`   | `/etc/systemd/system/`  | The unit. `Type=simple`, `Restart=always`, captures stdout to the log file. |
| `cpu-thermals.logrotate` | `/etc/logrotate.d/cpu-thermals` | Daily rotation, keep 30, compress, restart the unit on rotation. |
| `install.sh`             | (run from here)         | Copies the two files into place and enables the service. |

## How to run

The one-liner:

```bash
sudo ./install.sh
```

Or do it manually:

```bash
sudo install -d -m 0755 /var/log/cpu_thermals
sudo install -m 0644 cpu-thermals.service   /etc/systemd/system/
sudo install -m 0644 cpu-thermals.logrotate /etc/logrotate.d/cpu-thermals
sudo systemctl daemon-reload
sudo systemctl enable --now cpu-thermals.service
```

Verify:

```bash
sudo systemctl status cpu-thermals          # should be 'active (running)'
sudo tail -f /var/log/cpu_thermals/cpu_thermals.csv
sudo journalctl -u cpu-thermals -f          # human-readable banners / errors
```

## What you should see

`/var/log/cpu_thermals/cpu_thermals.csv`:

```csv
timestamp,node,sensor,celsius
2026-04-18T11:43:57-04:00,fleetnode-12,CPU0,42.0
2026-04-18T11:43:57-04:00,fleetnode-12,CPU1,40.0
2026-04-18T11:43:59-04:00,fleetnode-12,CPU0,42.0
2026-04-18T11:43:59-04:00,fleetnode-12,CPU1,40.0
...
```

`journalctl -u cpu-thermals` (banner + summary lines, never in the CSV):

```
fleetnode-12 systemd[1]: Started cpu-thermals.service - Continuous CPU thermal capture (cpu_thermals --csv -).
fleetnode-12 cpu-thermals[1234]: [cpu_thermals] recording CSV to stdout
```

After a few rotations:

```bash
$ sudo ls -la /var/log/cpu_thermals/
-rw-r--r-- 1 root root  4.2K Apr 18 04:00 cpu_thermals.csv         # current
-rw-r--r-- 1 root root  118K Apr 18 04:00 cpu_thermals.csv.1       # yesterday
-rw-r--r-- 1 root root   16K Apr 17 04:00 cpu_thermals.csv.2.gz    # day before
-rw-r--r-- 1 root root   16K Apr 16 04:00 cpu_thermals.csv.3.gz
...
```

Each `.csv.N` (and decompressed `.csv.N.gz`) starts with the `timestamp,node,sensor,celsius` header, because the rotation `postrotate` restarts the service and `cpu-thermals --csv -` always writes the header on stdout startup.

### Test the rotation now (don't wait a day)

```bash
sudo logrotate -f /etc/logrotate.d/cpu-thermals
sudo head -1 /var/log/cpu_thermals/cpu_thermals.csv          # should be the header
sudo zcat /var/log/cpu_thermals/cpu_thermals.csv.2.gz | head -1   # also the header
```

## Hooking into alerting / analysis tooling

The on-disk CSV is the integration point. Anything that can read CSV can plug in:

- **Datadog Agent**: a `logs:` source pointing at `/var/log/cpu_thermals/cpu_thermals.csv` with `parser: csv`.
- **Telegraf**: the `[[inputs.tail]]` plugin with `data_format = "csv"`.
- **Cron `awk` alert**: `awk -F, 'NR>1 && $4>95 {print}' /var/log/cpu_thermals/cpu_thermals.csv | mail -s "thermal alert" ops@…`.
- **pandas one-liner** ("any sensor over 95 °C in the last hour"):

  ```python
  import pandas as pd
  df = pd.read_csv("/var/log/cpu_thermals/cpu_thermals.csv", parse_dates=["timestamp"])
  hot = df[(df.celsius > 95) & (df.timestamp > pd.Timestamp.utcnow() - pd.Timedelta("1h"))]
  if not hot.empty: print(hot)
  ```

The schema (`timestamp, node, sensor, celsius`) is identical across machines, so concatenating CSVs from a fleet (`cat node-*.csv > all.csv`) Just Works.

## Hardening notes

The unit ships running as `root` for simplicity (works everywhere, no setup). For a hardened deployment:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin cpu_thermals
sudo chown cpu_thermals:cpu_thermals /var/log/cpu_thermals
sudo chmod 0755 /var/log/cpu_thermals
# Then in cpu-thermals.service uncomment:
#   User=cpu_thermals
#   Group=cpu_thermals
sudo systemctl daemon-reload && sudo systemctl restart cpu-thermals
```

`lm-sensors` reads from `/sys/class/hwmon/*` which is world-readable, so the dedicated user works without extra ACLs on most distros.

You can also uncomment `Nice=10` and `IOSchedulingClass=idle` in the unit to keep the monitor out of the way of real workloads — overkill for a process that wakes every 2 seconds, but trivially safe.

## Optional: Ansible fragment for fleet deployment

If you manage multiple hosts with Ansible, [`ansible/`](ansible/) contains a `cpu_thermals_systemd` role that templates the same unit and logrotate config and supports parameter overrides per host or per group. See [`ansible/README.md`](ansible/README.md). It's completely independent of the bare files above; pick one path or the other on a given host.

## What to look at next

- **[../1-simple-terminal/](../1-simple-terminal/)** for the live colored TUI without recording.
- **[../2-mprime-stress/](../2-mprime-stress/)** for a controlled load test that produces a labeled `temps.csv` + `phases.csv` you can correlate.
