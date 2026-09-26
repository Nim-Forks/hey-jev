#!/usr/bin/env bash
# Restart the hey-jev systemd service and health-check it.
set -e
sudo systemctl restart hey-jev
for i in $(seq 1 10); do
    sleep 1
    if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
        echo "[ok] hey-jev running"
        journalctl -u hey-jev -n 6 --no-pager
        exit 0
    fi
done
echo "[FAIL] not healthy:"; journalctl -u hey-jev -n 30 --no-pager
exit 1
