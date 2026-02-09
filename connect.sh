#!/bin/bash
# Quick connect/deploy script - use after initial setup.sh
# Usage: ./connect.sh [command]
#   ./connect.sh              - Show status and Gradio URL
#   ./connect.sh use <name>   - Switch to known IP (e.g., 2389, home)
#   ./connect.sh deploy       - Deploy latest code to robot
#   ./connect.sh restart      - Restart the conversation app
#   ./connect.sh logs         - Stream robot logs
#   ./connect.sh ssh          - SSH into robot

set -e

CONFIG_FILE="$HOME/.kayacan/config.env"
KNOWN_IPS_FILE="$HOME/.kayacan/known_ips.env"

# Load known IPs
[ -f "$KNOWN_IPS_FILE" ] && source "$KNOWN_IPS_FILE"

# Handle 'use' command to switch IPs
if [ "$1" = "use" ] && [ -n "$2" ]; then
    LOCATION_UPPER=$(echo "$2" | tr '[:lower:]' '[:upper:]')
    VAR_NAME="REACHY_IP_${LOCATION_UPPER}"
    eval "NEW_IP=\$$VAR_NAME"
    if [ -n "$NEW_IP" ]; then
        mkdir -p "$HOME/.kayacan"
        if [ -f "$CONFIG_FILE" ]; then
            sed -i '' "s/ROBOT_IP=\"[^\"]*\"/ROBOT_IP=\"$NEW_IP\"/" "$CONFIG_FILE"
        else
            echo "ROBOT_IP=\"$NEW_IP\"" > "$CONFIG_FILE"
            echo "SSH_PASS=\"root\"" >> "$CONFIG_FILE"
        fi
        echo "Switched to $2: $NEW_IP"
        # Test connection
        if curl -s --connect-timeout 2 "http://$NEW_IP:8000/api/daemon/status" &>/dev/null; then
            echo "Connection OK!"
        else
            echo "Warning: Cannot reach robot at $NEW_IP"
        fi
        exit 0
    else
        echo "Unknown location: $2"
        echo "Known locations:"
        grep "^REACHY_IP_" "$KNOWN_IPS_FILE" 2>/dev/null | sed 's/REACHY_IP_//;s/=/ = /'
        exit 1
    fi
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "No config found. Run ./setup.sh first or ./connect.sh use <location>"
    [ -f "$KNOWN_IPS_FILE" ] && echo "" && echo "Known locations:" && grep "^REACHY_IP_" "$KNOWN_IPS_FILE" | sed 's/REACHY_IP_//;s/=/ = /'
    exit 1
fi

source "$CONFIG_FILE"

ROBOT_USER="pollen"
DEST_PATH="/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app"

case "${1:-status}" in
    status)
        echo "Robot: $ROBOT_IP"
        echo ""
        # Get current app status
        STATUS=$(curl -s "http://$ROBOT_IP:8000/api/apps/current" 2>/dev/null || echo '{"error": "cannot connect"}')
        echo "App Status: $STATUS"
        echo ""
        # Try to get Gradio URL from recent logs
        echo "Looking for Gradio URL..."
        URL=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
            "journalctl -u reachy-mini-launcher --no-pager -n 100 2>/dev/null" | \
            grep -oE 'https://[a-z0-9]+\.gradio\.live' | tail -1)
        if [ -n "$URL" ]; then
            echo ""
            echo "========================================"
            echo "  Gradio URL: $URL"
            echo "========================================"
        else
            echo "No Gradio URL found. App may still be starting."
            echo "Run: ./connect.sh logs"
        fi
        ;;

    deploy)
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        echo "Deploying to $ROBOT_IP..."

        # Create .env for robot
        ROBOT_ENV="/tmp/kayacan_robot.env"
        cat > "$ROBOT_ENV" << EOF
USE_CLAWDBOT=true
OPENAI_API_KEY="$OPENAI_API_KEY"
ELEVENLABS_API_KEY="$ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID="$ELEVENLABS_VOICE_ID"
HONCHO_API_KEY="$HONCHO_API_KEY"
HONCHO_WORKSPACE_ID="reachy-mini"
CLAWDBOT_ENDPOINT="$CLAWDBOT_ENDPOINT"
CLAWDBOT_TOKEN="$CLAWDBOT_TOKEN"
CLAWDBOT_MODEL="$CLAWDBOT_MODEL"
EOF

        sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no -r \
            "$SCRIPT_DIR/pollen_app/src/reachy_mini_conversation_app/"* \
            "$ROBOT_USER@$ROBOT_IP:$DEST_PATH/"

        sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no \
            "$ROBOT_ENV" "$ROBOT_USER@$ROBOT_IP:$DEST_PATH/.env"

        rm "$ROBOT_ENV"
        echo "Deployed! Run './connect.sh restart' to apply changes."
        ;;

    restart)
        echo "Restarting app on $ROBOT_IP..."
        sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
            "sudo fuser -k 7862/tcp 2>/dev/null || true"
        curl -s -X POST "http://$ROBOT_IP:8000/api/apps/restart-current-app"
        echo ""
        echo "Restarted. Wait ~20s then run './connect.sh status' for URL."
        ;;

    logs)
        echo "Streaming logs from $ROBOT_IP (Ctrl+C to stop)..."
        sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
            "journalctl -u reachy-mini-launcher -f"
        ;;

    ssh)
        echo "Connecting to $ROBOT_IP..."
        sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP"
        ;;

    url)
        # Just get the URL
        URL=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
            "journalctl -u reachy-mini-launcher --no-pager -n 100 2>/dev/null" | \
            grep -oE 'https://[a-z0-9]+\.gradio\.live' | tail -1)
        if [ -n "$URL" ]; then
            echo "$URL"
        else
            echo "No URL found" >&2
            exit 1
        fi
        ;;

    ips|list)
        echo "Known Reachy locations:"
        grep "^REACHY_IP_" "$KNOWN_IPS_FILE" 2>/dev/null | sed 's/REACHY_IP_//;s/=/ = /' || echo "No known IPs saved"
        echo ""
        echo "Current: $ROBOT_IP"
        ;;

    wake)
        echo "Waking up Reachy at $ROBOT_IP..."
        curl -s -X POST "http://$ROBOT_IP:8000/api/daemon/start?wake_up=true"
        echo ""
        ;;

    sleep)
        echo "Putting Reachy to sleep..."
        curl -s -X POST "http://$ROBOT_IP:8000/api/move/play/goto_sleep"
        echo ""
        ;;

    *)
        echo "Usage: ./connect.sh [command]"
        echo ""
        echo "Commands:"
        echo "  status      - Show status and Gradio URL (default)"
        echo "  use <name>  - Switch to known IP (e.g., 2389, home)"
        echo "  ips         - List known IPs"
        echo "  deploy      - Deploy latest code to robot"
        echo "  restart     - Restart the conversation app"
        echo "  logs        - Stream robot logs"
        echo "  ssh         - SSH into robot"
        echo "  url         - Just print the Gradio URL"
        echo "  wake        - Wake up Reachy"
        echo "  sleep       - Put Reachy to sleep"
        ;;
esac
