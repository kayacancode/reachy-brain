#!/bin/bash
# Deploy everything needed for talk mode to the robot
# Usage: ./deploy_talk.sh [ROBOT_IP]

set -e

# Load config if exists
CONFIG_FILE="$HOME/.reachy-brain/config.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

# Get robot IP from arg or config
ROBOT_IP="${1:-${ROBOT_IP:-192.168.23.66}}"
ROBOT_USER="pollen"
ROBOT_PASS="${SSH_PASS:-root}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  Deploying Talk Mode to Reachy Mini"
echo "============================================"
echo ""
echo "Robot: $ROBOT_IP"
echo ""

# Check connection
echo "1. Checking robot connection..."
if ! curl -s --connect-timeout 3 "http://$ROBOT_IP:8000/api/daemon/status" > /dev/null 2>&1; then
    echo "   Cannot reach robot daemon at $ROBOT_IP:8000"
    echo "   Make sure robot is powered on and daemon is running:"
    echo "   ./wake.sh $ROBOT_IP"
    exit 1
fi
echo "   Robot daemon OK"

# Deploy bridge
echo ""
echo "2. Deploying bridge..."
sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" "mkdir -p ~/bridge"
sshpass -p "$ROBOT_PASS" scp -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/bridge/reachy_bridge.py" \
    "$ROBOT_USER@$ROBOT_IP:~/bridge/"
echo "   Bridge deployed to ~/bridge/"

# Deploy talk mode files
echo ""
echo "3. Deploying talk mode files..."
sshpass -p "$ROBOT_PASS" scp -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/talk_wireless.py" \
    "$SCRIPT_DIR/face_registry.py" \
    "$SCRIPT_DIR/vision.py" \
    "$SCRIPT_DIR/memory.py" \
    "$SCRIPT_DIR/tools.py" \
    "$SCRIPT_DIR/run_talk.sh" \
    "$SCRIPT_DIR/start_all.sh" \
    "$SCRIPT_DIR/audio_server.py" \
    "$ROBOT_USER@$ROBOT_IP:~/"
echo "   Talk mode files deployed to ~/"

# Deploy config
echo ""
echo "4. Deploying config..."
sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" "mkdir -p ~/.reachy-brain"
if [ -f "$CONFIG_FILE" ]; then
    sshpass -p "$ROBOT_PASS" scp -o StrictHostKeyChecking=no \
        "$CONFIG_FILE" \
        "$ROBOT_USER@$ROBOT_IP:~/.reachy-brain/config.env"
    # Override ROBOT_IP to localhost on the robot (it runs locally)
    sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
        "sed -i 's/^ROBOT_IP=.*/ROBOT_IP=\"127.0.0.1\"/' ~/.reachy-brain/config.env"
    echo "   Config deployed (ROBOT_IP set to 127.0.0.1 for local operation)"
else
    echo "   No config file found at $CONFIG_FILE - skipping"
fi

# Make scripts executable
sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
    "chmod +x ~/run_talk.sh ~/start_all.sh ~/audio_server.py ~/bridge/reachy_bridge.py"

# Kill existing bridge if running
echo ""
echo "5. Starting bridge..."
sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
    "pkill -f reachy_bridge.py 2>/dev/null || true"
sleep 1

# Start bridge in background
sshpass -p "$ROBOT_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
    "cd ~/bridge && nohup /restore/venvs/mini_daemon/bin/python3 reachy_bridge.py --no-listen > /tmp/bridge.log 2>&1 &"
sleep 3

# Verify bridge
if curl -s --connect-timeout 3 "http://$ROBOT_IP:9000/status" > /dev/null 2>&1; then
    echo "   Bridge running on port 9000"
else
    echo "   Bridge may still be starting..."
    echo "   Check: curl http://$ROBOT_IP:9000/status"
fi

echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "  1. Make sure OpenClaw is running on your Mac:"
echo "     openclaw gateway"
echo ""
echo "  2. SSH to robot and start talk mode:"
echo "     ssh $ROBOT_USER@$ROBOT_IP"
echo "     ./run_talk.sh"
echo ""
echo "  Or run directly:"
echo "     sshpass -p '$ROBOT_PASS' ssh $ROBOT_USER@$ROBOT_IP './run_talk.sh'"
echo ""
