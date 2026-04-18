#!/usr/bin/env bash
#
# One-shot installer for the cpu_thermals systemd unit + logrotate config.
# Run from this directory. Requires sudo (writes to /etc and /var/log).
#
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "error: this example is Linux-only (systemd)" >&2
    exit 1
fi

if ! command -v cpu-thermals >/dev/null 2>&1; then
    echo "error: 'cpu-thermals' is not on PATH. Install it first; see ../../README.md." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo install -d -m 0755 /var/log/cpu_thermals
sudo install -m 0644 "$SCRIPT_DIR/cpu-thermals.service"   /etc/systemd/system/cpu-thermals.service
sudo install -m 0644 "$SCRIPT_DIR/cpu-thermals.logrotate" /etc/logrotate.d/cpu-thermals
sudo systemctl daemon-reload
sudo systemctl enable --now cpu-thermals.service

echo
echo "Installed. Useful next steps:"
echo "    sudo systemctl status cpu-thermals"
echo "    sudo tail -f /var/log/cpu_thermals/cpu_thermals.csv"
echo "    sudo journalctl -u cpu-thermals -f          # banner / summary lines"
echo "    sudo logrotate -f /etc/logrotate.d/cpu-thermals   # test rotation now"
