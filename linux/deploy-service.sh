#!/usr/bin/env bash
# Generate a systemd unit for hey-jev and install it, filling in the current
# user, venv and checkout paths. Supports several checkouts on one box (each
# with its own service name and REMOTE_PORT), e.g. beta + production:
#   bash deploy-service.sh               -> service name defaults to hey-jev
#   bash deploy-service.sh hey-jev-prod  -> second instance, own checkout dir
# Paths come from the script's location: <checkout>/linux/deploy-service.sh.
set -e
cd "$(dirname "$0")"

LINUX_DIR=$(pwd)
CHECKOUT_DIR=$(dirname "$LINUX_DIR")
ENV_FILE="$CHECKOUT_DIR/.env"
RUN_USER=$(whoami)
RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
VENV_PY="$LINUX_DIR/.venv/bin/python"
SERVICE_NAME="${1:-hey-jev}"
UNIT_FILE="/etc/systemd/system/$SERVICE_NAME.service"

cat > /tmp/$SERVICE_NAME.service <<EOF
[Unit]
Description=Hey Jev remote (web mic/PTT server)
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$RUN_USER
Environment=PYTHONUTF8=1
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u)
WorkingDirectory=$LINUX_DIR
ExecStart=$VENV_PY -u -X utf8 remote.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/$SERVICE_NAME.service "$UNIT_FILE"
sudo systemctl daemon-reload
# stop a previous instance of the same service before enabling the new name
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
sudo systemctl enable --now "$SERVICE_NAME"

PORT=$(grep -E "^REMOTE_PORT=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
PORT=${PORT:-8765}

for i in $(seq 1 10); do
    sleep 1
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        echo "[ok] $SERVICE_NAME running as $RUN_USER (dir: $SERVICE_DIR)"
        exit 0
    fi
done

echo "[FAIL] service did not come up; logs:"
sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
exit 1
