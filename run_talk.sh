#!/bin/bash
# Run the enhanced talk_wireless.py with all features
#
# Usage on the robot:
#   ./run_talk.sh
#
# Or with custom settings:
#   ENABLE_FACE_RECOGNITION=false ./run_talk.sh

# Load and export environment variables from config
if [ -f ~/.kayacan/config.env ]; then
    set -a  # auto-export all variables
    source ~/.kayacan/config.env
    set +a
fi

# Defaults
export ROBOT_IP="${ROBOT_IP:-127.0.0.1}"
export ENABLE_FACE_RECOGNITION="${ENABLE_FACE_RECOGNITION:-true}"
export ENABLE_HONCHO="${ENABLE_HONCHO:-true}"
export ENABLE_TOOLS="${ENABLE_TOOLS:-true}"

echo "Starting Reachy Talk with:"
echo "  ROBOT_IP=$ROBOT_IP"
echo "  ENABLE_FACE_RECOGNITION=$ENABLE_FACE_RECOGNITION"
echo "  ENABLE_HONCHO=$ENABLE_HONCHO"
echo "  ENABLE_TOOLS=$ENABLE_TOOLS"
echo ""

python3 talk_wireless.py
