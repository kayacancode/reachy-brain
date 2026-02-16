#!/bin/bash
# Start everything with one command
# Usage: ./start_all.sh [workspace]
#
# This script:
# 1. Wakes up the robot daemon
# 2. Starts the audio server
# 3. Starts the camera server
# 4. Runs talk_wireless.py

WORKSPACE="${1:-openclaw}"

echo "========================================"
echo "  Starting Reachy Talk System"
echo "========================================"
echo ""

# 1. Start daemon if not running
if ! curl -s "http://127.0.0.1:8000/api/daemon/status" > /dev/null 2>&1; then
    echo "Starting daemon..."
    nohup /venvs/mini_daemon/bin/python -m reachy_mini.daemon.app.main > ~/daemon.log 2>&1 &

    # Wait for daemon to be ready
    for i in {1..15}; do
        if curl -s "http://127.0.0.1:8000/api/daemon/status" > /dev/null 2>&1; then
            echo "Daemon started"
            break
        fi
        echo "Waiting for daemon... ($i/15)"
        sleep 2
    done
else
    echo "Daemon already running"
fi

# Wake up the robot
echo "Waking up robot..."
curl -s -X POST "http://127.0.0.1:8000/api/daemon/start?wake_up=true"
sleep 3

# Verify robot is awake
STATUS=$(curl -s "http://127.0.0.1:8000/api/daemon/status" 2>/dev/null | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
echo "Robot state: $STATUS"

# 2. Start audio server (uses PulseAudio - no conflicts with daemon)
if ! pgrep -f audio_server > /dev/null; then
    echo "Starting audio server..."
    nohup python3 ~/audio_server.py > ~/audio.log 2>&1 &
    sleep 2
else
    echo "Audio server already running"
fi

# 3. Start camera if not running
if ! pgrep -f camera_server > /dev/null; then
    echo "Starting camera..."
    nohup python3 ~/camera_server.py > ~/camera.log 2>&1 &
    sleep 2
else
    echo "Camera already running"
fi

echo ""
echo "All services started. Launching talk mode..."
echo ""

# 4. Run talk
./run_talk.sh "$WORKSPACE"
