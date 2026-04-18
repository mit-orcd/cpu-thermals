# Role: `cpu_thermals_systemd`

Install and run [cpu_thermals](https://github.com/cnh/cpu_thermals) as a `systemd` unit on a Linux host, with `logrotate` keeping the captured CSV bounded.

The role does **not** install the `cpu_thermals` Python package — that's left to whatever deployment story your fleet already uses (pip, system package, wheel, container, etc.). It asserts the binary is present at `cpu_thermals_binary_path` and fails with a clear message if not.

## What it does

1. Asserts the `cpu-thermals` binary is present.
2. Creates the log directory.
3. Templates `/etc/systemd/system/<service>.service` from `cpu-thermals.service.j2` (notifies reload + restart).
4. Templates `/etc/logrotate.d/<service>` from `cpu-thermals.logrotate.j2` (or removes it when disabled).
5. `daemon-reload`, then enables and starts the service.

## Variables

All defined in [`defaults/main.yml`](defaults/main.yml). Override in playbook vars / host_vars / group_vars.

| Variable | Default | Notes |
| --- | --- | --- |
| `cpu_thermals_binary_path` | `/usr/local/bin/cpu-thermals` | Asserted to exist before applying. |
| `cpu_thermals_log_dir` | `/var/log/cpu_thermals` | |
| `cpu_thermals_log_file` | `cpu_thermals.csv` | |
| `cpu_thermals_sample_interval` | `2.0` | Seconds; positional arg to `cpu-thermals`. |
| `cpu_thermals_user` | `root` | Service identity + log dir owner. |
| `cpu_thermals_group` | `root` | |
| `cpu_thermals_service_name` | `cpu-thermals` | Used as the unit name and the logrotate filename. |
| `cpu_thermals_service_state` | `started` | `started` / `stopped` / `restarted`. |
| `cpu_thermals_service_enabled` | `true` | Enable on boot. |
| `cpu_thermals_restart_sec` | `5` | systemd `RestartSec=`. |
| `cpu_thermals_logrotate_enabled` | `true` | Set false to skip the logrotate config. |
| `cpu_thermals_logrotate_frequency` | `daily` | `daily` / `weekly` / `monthly`. |
| `cpu_thermals_logrotate_count` | `30` | Archives to keep. |

## Example invocation

```yaml
- hosts: thermal_capture
  become: true
  roles:
    - role: cpu_thermals_systemd
      vars:
        cpu_thermals_sample_interval: 5.0
        cpu_thermals_logrotate_count: 14
        cpu_thermals_user: cpu_thermals    # if you've created a dedicated user
        cpu_thermals_group: cpu_thermals
```

## Relationship to the bare files in `../../`

The role's templates render — with default vars — to *exactly* the contents of the static `cpu-thermals.service` and `cpu-thermals.logrotate` files one directory up. The static files are useful when reading the manual install path; the templates are the parameterised version Ansible applies.

Pick one path or the other on a given host. Don't mix.

## Handlers

- `Reload systemd` — runs `daemon-reload` after the unit file changes.
- `Restart cpu_thermals` — restarts the service to pick up unit changes.

(The logrotate file change does not need a handler; logrotate re-reads its config on every run.)
