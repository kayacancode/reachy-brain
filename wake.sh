#!/bin/bash
# Wake up Reachy Mini robot
# Usage: ./wake.sh [IP]

# Load config if exists
CONFIG_FILE="$HOME/.reachy-brain/config.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

IP="${1:-${ROBOT_IP:-192.168.23.66}}"

echo "Waking up Reachy at $IP..."

# Start daemon with wake_up (handles both daemon start and wake up)
response=$(curl -s -X POST "http://$IP:8000/api/daemon/start?wake_up=true" --connect-timeout 5)

if echo "$response" | grep -q "job_id"; then
    echo "Daemon starting and robot waking up..."
    sleep 3
    echo "Reachy is awake!"
elif echo "$response" | grep -q "already running"; then
    # Daemon already running, just wake up
    curl -s -X POST "http://$IP:8000/api/move/play/wake_up" --connect-timeout 5 > /dev/null
    echo "Reachy is awake!"
else
    echo "Response: $response"
fi
