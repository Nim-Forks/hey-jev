#!/usr/bin/env bash
# Generate a systemd unit for hey-jev and install it, filling in the current
# user, home and venv paths. Usage:
#   bash deploy-service.sh            -> service name defaults to hey-jev
#   bash deploy-service.sh my-name    -> service name my-name
set -e
cd "$(dirname "$0")"

RUN_USER=$(whoami)
RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
SERVICE_DIR="$RUN_HOME/hey-jev"
VENV_PY="$SERVICE_DIR/.venv/bin/python"
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
WorkingDirectory=$SERVICE_DIR
ExecStart=$VENV_PY -u -X utf8 siri.py --remote
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

PORT=$(grep -E "^REMOTE_PORT=" .env 2>/dev/null | head -1 | cut -d= -f2-)
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
