#!/usr/bin/env bash
# deploy-combos.sh — deploy new code to every hey-jev combo instance on this box.
#
# Usage (from a checkout, on the geekom):  bash linux/deploy-combos.sh [--with-beta]
#   1. git pull --ff-only in the prod checkout (combos symlink shared/ from it,
#      so one pull updates the shared code for all of them)
#   2. refresh the per-combo entry copies (linux/remote.py + linux/siri.py —
#      these are real copies because Python 3.11+ resolves symlinked script dirs)
#   3. restart all hey-jev-<combo>.service units
#   4. health-check every REMOTE_PORT and print a table
#
# --with-beta also rsyncs shared/ into the beta checkout (~/hey-jev) and
# restarts hey-jev.service. alpha (win11) is separate: git pull + its own
# restart script there.
set -e
BASE="$HOME/hey-jev-prod"

cd "$BASE"
echo "== git pull"
git pull --ff-only
COMMIT=$(git log --oneline -1)
echo "deploying: $COMMIT"

echo "== refreshing combo entry files"
COMBOS=$(ls ~/combo)
for name in $COMBOS; do
  d="$HOME/combo/$name"
  [ -d "$d/linux" ] || { echo "skip $name (no linux dir)"; continue; }
  cp "$BASE/linux/remote.py" "$BASE/linux/siri.py" "$d/linux/"
done

echo "== restarting combo services"
UNITS=""
for name in $COMBOS; do
  UNITS="$UNITS hey-jev-$name.service"
done
# shellcheck disable=SC2086
sudo systemctl restart $UNITS

echo "== health"
declare -A PORT
for name in $COMBOS; do
  PORT[$name]=$(grep -E '^REMOTE_PORT=' "$HOME/combo/$name/.env" | head -1 | cut -d= -f2)
done
ok=0; total=0
for _ in $(seq 1 30); do
  sleep 3
  ok=0; total=0
  for name in $COMBOS; do
    total=$((total + 1))
    curl -fsS -m 2 "http://127.0.0.1:${PORT[$name]}/health" >/dev/null 2>&1 && ok=$((ok + 1))
  done
  [ "$ok" -eq "$total" ] && break
done
for name in $COMBOS; do
  state=DOWN
  curl -fsS -m 2 "http://127.0.0.1:${PORT[$name]}/health" >/dev/null 2>&1 && state=ok
  printf "%-20s :%s  %s\n" "$name" "${PORT[$name]}" "$state"
done
echo "$ok/$total healthy — $COMMIT"

if [ "${1:-}" = "--with-beta" ]; then
  echo "== beta"
  rsync -rc --exclude '__pycache__' --exclude 'cache' "$BASE/shared/" "$HOME/hey-jev/shared/"
  sudo systemctl restart hey-jev.service
  sleep 6
  for _ in $(seq 1 15); do
    curl -fsS -m 2 "http://127.0.0.1:8765/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS -m 2 "http://127.0.0.1:8765/health" >/dev/null 2>&1 && echo "beta (8765): ok" || echo "beta (8765): DOWN"
fi

[ "$ok" -eq "$total" ]
