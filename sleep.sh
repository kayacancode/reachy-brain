#!/bin/bash
# Put Reachy Mini robot to sleep
# Usage: ./sleep.sh [IP]

# Load config if exists
CONFIG_FILE="$HOME/.kayacan/config.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

IP="${1:-${ROBOT_IP:-192.168.23.66}}"

echo "Putting Reachy to sleep at $IP..."
curl -s -X POST "http://$IP:8000/api/move/play/goto_sleep" --connect-timeout 5 > /dev/null
echo "Reachy is asleep."
