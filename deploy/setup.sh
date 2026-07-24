#!/usr/bin/env bash
# Set up podcast-radar-bot on an Ubuntu VPS.
# Run from the project root (where main.py + requirements.txt live).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null; then
  echo "python3 not found — install it first (apt install -y python3 python3-venv)"; exit 1
fi

echo "Creating venv..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
echo "Installing requirements..."
./venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo "WARNING: .env not found. Copy .env.example -> .env and fill in keys, SHOW, and channel id."
else
  echo ".env present."
fi

echo "Done. Next:"
echo "  1) ./venv/bin/python telegram_check.py   # confirm channel access"
echo "  2) sudo cp deploy/podcast-radar.service deploy/podcast-radar.timer /etc/systemd/system/"
echo "  3) edit the unit paths if the project isn't at /opt/podcast-radar-bot"
echo "  4) sudo systemctl daemon-reload && sudo systemctl enable --now podcast-radar.timer"
echo "  5) systemctl list-timers podcast-radar.timer"
