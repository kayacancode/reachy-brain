#!/bin/bash
# Put Reachy Mini robot to sleep
# Usage: ./sleep.sh [IP]

IP="${1:-192.168.23.66}"

echo "Putting Reachy to sleep at $IP..."
curl -s -X POST "http://$IP:8000/api/move/play/goto_sleep" --connect-timeout 5 > /dev/null
echo "Reachy is asleep."
