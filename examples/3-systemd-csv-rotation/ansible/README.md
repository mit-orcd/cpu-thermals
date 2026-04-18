# Optional Ansible fragment

A self-contained Ansible role (`cpu_thermals_systemd`) that deploys the same systemd unit + logrotate config as the bare files in the parent directory, but parameterised so per-host or per-group overrides are easy.

This fragment is **optional**. If you're managing a single host, the manual install path documented in the parent [`README.md`](../README.md) (or `../install.sh`) is simpler. The fragment is here for users running fleets.

The fragment lives entirely under `ansible/` and never touches the bare files in the parent directory. Pick one path or the other on a given host; don't mix.

## Three ways to use it

### Mode 1 — Standalone playbook (simplest)

Treat this directory as a self-contained Ansible bundle.

```bash
cd examples/3-systemd-csv-rotation/ansible
cat > inventory.ini <<'EOF'
[thermal_capture]
node-01.example.com
node-02.example.com
EOF
ansible-playbook -i inventory.ini site.yml
```

No collection involvement, no Galaxy. Edit `site.yml` to override variables (see [`roles/cpu_thermals_systemd/README.md`](roles/cpu_thermals_systemd/README.md) for the full list).

### Mode 2 — Vendor the role into your existing collection

If you already maintain a collection (say `mycorp.observability`), the role is designed to drop in verbatim:

```bash
cp -r examples/3-systemd-csv-rotation/ansible/roles/cpu_thermals_systemd \
      <your-collection-root>/roles/cpu_thermals_systemd
```

Then reference it from any playbook in your collection:

```yaml
- hosts: thermal_capture
  become: true
  roles:
    - mycorp.observability.cpu_thermals_systemd
```

The role uses only `ansible.builtin.*` modules, so it has no collection dependencies of its own.

### Mode 3 — Build it as your own Galaxy collection

A sample [`galaxy.yml`](galaxy.yml) is provided so this directory is already collection-shaped. The literal `namespace: local` placeholder will not pass Galaxy validation; you must edit it first:

```bash
cd examples/3-systemd-csv-rotation/ansible

# 1. Edit galaxy.yml: set your namespace, name, authors, repository.
# 2. Build:
ansible-galaxy collection build

# 3. Publish (requires a Galaxy token):
ansible-galaxy collection publish <your_namespace>-<your_name>-0.1.0.tar.gz \
    --token "$ANSIBLE_GALAXY_TOKEN"
```

After publishing, anyone can install with:

```bash
ansible-galaxy collection install <your_namespace>.<your_name>
```

and reference the role as `<your_namespace>.<your_name>.cpu_thermals_systemd`.

## Layout

```
ansible/
├── README.md                 # this file
├── galaxy.yml                # collection metadata (mode 3)
├── site.yml                  # example standalone playbook (mode 1)
└── roles/
    └── cpu_thermals_systemd/
        ├── README.md         # role-level docs (variables, what it does)
        ├── defaults/main.yml
        ├── handlers/main.yml
        ├── meta/main.yml     # galaxy_info for ansible-lint
        ├── tasks/main.yml
        └── templates/
            ├── cpu-thermals.service.j2
            └── cpu-thermals.logrotate.j2
```

## Local validation (no target host needed)

```bash
ansible-playbook --syntax-check site.yml
ansible-lint roles/cpu_thermals_systemd/
ansible-galaxy collection build --force          # mode 3 sanity check
```

## What the role deliberately does NOT do

- Install the `cpu_thermals` Python package itself. Out of scope; depends on whether your fleet uses pip, a system package, a wheel from artifactory, etc. The role asserts the binary is present at `cpu_thermals_binary_path` and fails with a clear message if not.
- Manage the underlying sensor tool (`lm-sensors` on Linux). Same reason.
- Use `ansible.builtin.copy` of the static parent-directory files. Templating with explicit variables is the Ansible way; mixing copy-of-static-file with templated config would be confusing.
