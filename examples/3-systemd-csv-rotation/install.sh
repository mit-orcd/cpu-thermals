#!/usr/bin/env bash
#
# One-shot installer for the cpu_thermals systemd unit + logrotate config.
# Run from this directory. Requires sudo (writes to /etc and /var/log).
#
# Resolves the actual cpu-thermals binary path on this host and
# substitutes it into the unit's ExecStart= line before installing, so
# the service works whether the binary lives at /usr/local/bin/,
# /usr/bin/, ~/.local/bin/, a venv path, or anywhere else on PATH.
# (The static unit ships with /usr/local/bin/cpu-thermals as a sensible
# default, which is what `pip install` typically picks; the substitution
# below silently fixes the common-but-not-guaranteed case.)
#
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "error: this example is Linux-only (systemd)" >&2
    exit 1
fi

if ! BIN_PATH=$(command -v cpu-thermals); then
    echo "error: 'cpu-thermals' is not on PATH. Install it first;" >&2
    echo "       see ../../README.md for install options." >&2
    exit 1
fi
echo ">> Detected cpu-thermals at: $BIN_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Render a copy of the unit with the correct ExecStart= path so the
# service starts cleanly on hosts where the binary isn't at the static
# default. Uses '|' as the sed delimiter because paths contain '/'.
TMP_UNIT="$(mktemp)"
trap 'rm -f "$TMP_UNIT"' EXIT
sed "s|^ExecStart=/usr/local/bin/cpu-thermals|ExecStart=${BIN_PATH}|" \
    "$SCRIPT_DIR/cpu-thermals.service" > "$TMP_UNIT"

# Sanity-check: confirm the substitution actually fired (the user didn't
# already edit the unit file to use a different path).
if ! grep -q "^ExecStart=${BIN_PATH}" "$TMP_UNIT"; then
    echo "error: failed to patch ExecStart= in the unit file." >&2
    echo "       Did you customise cpu-thermals.service? Either revert" >&2
    echo "       the ExecStart= line to the shipped default, or install" >&2
    echo "       the unit by hand." >&2
    exit 1
fi

sudo install -d -m 0755 /var/log/cpu_thermals
sudo install -m 0644 "$TMP_UNIT"                          /etc/systemd/system/cpu-thermals.service
sudo install -m 0644 "$SCRIPT_DIR/cpu-thermals.logrotate" /etc/logrotate.d/cpu-thermals
sudo systemctl daemon-reload
sudo systemctl enable --now cpu-thermals.service

echo
echo "Installed. Useful next steps:"
echo "    sudo systemctl status cpu-thermals"
echo "    sudo tail -f /var/log/cpu_thermals/cpu_thermals.csv"
echo "    sudo journalctl -u cpu-thermals -f          # banner / summary lines"
echo "    sudo logrotate -f /etc/logrotate.d/cpu-thermals   # test rotation now"
