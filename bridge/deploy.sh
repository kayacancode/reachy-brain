#!/usr/bin/env bash
# Deploy Reachy Bridge to the robot and start it
set -euo pipefail

REACHY_HOST="10.0.0.68"
REACHY_USER="pollen"
REACHY_PASS="root"
REMOTE_DIR="/home/pollen/bridge"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 Deploying bridge to Reachy..."

# Create remote dir
sshpass -p "$REACHY_PASS" ssh "$REACHY_USER@$REACHY_HOST" "mkdir -p $REMOTE_DIR"

# Copy bridge script
sshpass -p "$REACHY_PASS" scp "$SCRIPT_DIR/reachy_bridge.py" "$REACHY_USER@$REACHY_HOST:$REMOTE_DIR/reachy_bridge.py"

echo "✅ Deployed to $REMOTE_DIR"
echo ""
echo "Starting Cooper's SDK bridge..."

# Kill any existing bridge
sshpass -p "$REACHY_PASS" ssh "$REACHY_USER@$REACHY_HOST" "pkill -f reachy_bridge.py 2>/dev/null || true"
sleep 1

# Start bridge in background with nohup
# Note: Bridge will auto-detect macOS host, or set via --macos-host argument
sshpass -p "$REACHY_PASS" ssh "$REACHY_USER@$REACHY_HOST" \
  "cd $REMOTE_DIR && nohup /restore/venvs/mini_daemon/bin/python3 reachy_bridge.py > /tmp/bridge.log 2>&1 &"

sleep 3  # Give more time for SDK initialization

# Check if it started
if curl -s "http://$REACHY_HOST:9000/status" > /dev/null 2>&1; then
  echo "🌉 Cooper's SDK bridge is running on http://$REACHY_HOST:9000"
  echo ""
  echo "Bridge Status:"
  curl -s "http://$REACHY_HOST:9000/status" | python3 -m json.tool
  echo ""
  echo "🎤 Bridge will auto-start continuous listening when macOS voice loop connects"
else
  echo "⚠️  Bridge may still be starting. Check: curl http://$REACHY_HOST:9000/status"
  echo "Logs: sshpass -p root ssh pollen@$REACHY_HOST 'cat /tmp/bridge.log'"
fi
