#!/bin/bash
# KayaCan Setup Script - Quick setup for Reachy Mini with Claude Brain
# Run this when you move to a new location or set up fresh

set -e

echo "=========================================="
echo "  KayaCan - Reachy Mini Setup"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DEFAULT_SSH_PASS="root"
ROBOT_USER="pollen"

# Config file location
CONFIG_FILE="$HOME/.kayacan/config.env"
mkdir -p "$HOME/.kayacan"

# Function to discover robot on network
discover_robot() {
    echo -e "${YELLOW}Searching for Reachy Mini on network...${NC}"

    # Try mDNS first (reachy-mini.local)
    if ping -c 1 -W 2 reachy-mini.local &>/dev/null; then
        ROBOT_IP=$(ping -c 1 reachy-mini.local | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)
        echo -e "${GREEN}Found robot via mDNS: $ROBOT_IP${NC}"
        return 0
    fi

    # Try common subnet scan
    echo "mDNS not found, scanning local network..."
    LOCAL_SUBNET=$(ip route 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1 || ifconfig 2>/dev/null | grep -oE '192\.168\.[0-9]+\.[0-9]+' | head -1 || echo "")

    if [ -n "$LOCAL_SUBNET" ]; then
        SUBNET_PREFIX=$(echo "$LOCAL_SUBNET" | cut -d. -f1-3)
        for i in {1..254}; do
            IP="$SUBNET_PREFIX.$i"
            if curl -s --connect-timeout 0.5 "http://$IP:8000/api/daemon/status" &>/dev/null; then
                ROBOT_IP="$IP"
                echo -e "${GREEN}Found robot at: $ROBOT_IP${NC}"
                return 0
            fi
        done
    fi

    return 1
}

# Function to test robot connection
test_connection() {
    local ip=$1
    echo -n "Testing connection to $ip... "
    if curl -s --connect-timeout 3 "http://$ip:8000/api/daemon/status" &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        return 1
    fi
}

# Function to get Mac's IP for OpenClaw endpoint
get_mac_ip() {
    # Get the IP that can reach the robot
    if [ -n "$ROBOT_IP" ]; then
        MAC_IP=$(ip route get "$ROBOT_IP" 2>/dev/null | grep -oP 'src \K[0-9.]+' || \
                 route get "$ROBOT_IP" 2>/dev/null | grep interface | awk '{print $2}' | xargs ipconfig getifaddr 2>/dev/null || \
                 ifconfig 2>/dev/null | grep -oE '192\.168\.[0-9]+\.[0-9]+' | head -1 || \
                 echo "localhost")
    else
        MAC_IP=$(ifconfig 2>/dev/null | grep -oE '192\.168\.[0-9]+\.[0-9]+' | head -1 || echo "localhost")
    fi
    echo "$MAC_IP"
}

# Step 1: Find or set robot IP
echo "Step 1: Robot Connection"
echo "------------------------"

if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
    echo "Found existing config: ROBOT_IP=$ROBOT_IP"
    read -p "Use existing IP? [Y/n]: " use_existing
    if [[ "$use_existing" =~ ^[Nn] ]]; then
        ROBOT_IP=""
    fi
fi

if [ -z "$ROBOT_IP" ]; then
    read -p "Enter robot IP (or press Enter to auto-discover): " ROBOT_IP

    if [ -z "$ROBOT_IP" ]; then
        if ! discover_robot; then
            echo -e "${RED}Could not auto-discover robot.${NC}"
            read -p "Enter robot IP manually: " ROBOT_IP
        fi
    fi
fi

if ! test_connection "$ROBOT_IP"; then
    echo -e "${RED}Cannot connect to robot at $ROBOT_IP${NC}"
    echo "Make sure:"
    echo "  1. Robot is powered on"
    echo "  2. Connected to same network"
    echo "  3. Daemon is running"
    exit 1
fi

# Step 2: Get SSH password
echo ""
echo "Step 2: SSH Credentials"
echo "-----------------------"
read -p "SSH password for $ROBOT_USER@$ROBOT_IP [$DEFAULT_SSH_PASS]: " SSH_PASS
SSH_PASS=${SSH_PASS:-$DEFAULT_SSH_PASS}

# Test SSH
echo -n "Testing SSH... "
if sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$ROBOT_USER@$ROBOT_IP" "echo ok" &>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Check SSH password and try again."
    exit 1
fi

# Step 3: API Keys
echo ""
echo "Step 3: API Keys"
echo "----------------"
echo "Leave blank to keep existing value."
echo ""

# Load existing values if any
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

read -p "OpenAI API Key (for Whisper) [${OPENAI_API_KEY:0:10}...]: " new_openai
[ -n "$new_openai" ] && OPENAI_API_KEY="$new_openai"

read -p "ElevenLabs API Key [${ELEVENLABS_API_KEY:0:10}...]: " new_eleven
[ -n "$new_eleven" ] && ELEVENLABS_API_KEY="$new_eleven"

read -p "ElevenLabs Voice ID [${ELEVENLABS_VOICE_ID:-21m00Tcm4TlvDq8ikWAM}]: " new_voice
ELEVENLABS_VOICE_ID=${new_voice:-${ELEVENLABS_VOICE_ID:-21m00Tcm4TlvDq8ikWAM}}

read -p "Honcho API Key (optional) [${HONCHO_API_KEY:0:10}...]: " new_honcho
[ -n "$new_honcho" ] && HONCHO_API_KEY="$new_honcho"

# Step 4: OpenClaw setup
echo ""
echo "Step 4: OpenClaw (Clawdbot) Setup"
echo "----------------------------------"
MAC_IP=$(get_mac_ip)
DEFAULT_ENDPOINT="http://$MAC_IP:18789/v1/chat/completions"

read -p "OpenClaw endpoint [$DEFAULT_ENDPOINT]: " CLAWDBOT_ENDPOINT
CLAWDBOT_ENDPOINT=${CLAWDBOT_ENDPOINT:-$DEFAULT_ENDPOINT}

read -p "OpenClaw token [${CLAWDBOT_TOKEN:0:10}...]: " new_token
[ -n "$new_token" ] && CLAWDBOT_TOKEN="$new_token"

read -p "Claude model [${CLAWDBOT_MODEL:-claude-sonnet-4-20250514}]: " new_model
CLAWDBOT_MODEL=${new_model:-${CLAWDBOT_MODEL:-claude-sonnet-4-20250514}}

# Save config locally
echo ""
echo "Saving configuration..."
cat > "$CONFIG_FILE" << EOF
# KayaCan Configuration - Generated $(date)
ROBOT_IP="$ROBOT_IP"
SSH_PASS="$SSH_PASS"
OPENAI_API_KEY="$OPENAI_API_KEY"
ELEVENLABS_API_KEY="$ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID="$ELEVENLABS_VOICE_ID"
HONCHO_API_KEY="$HONCHO_API_KEY"
CLAWDBOT_ENDPOINT="$CLAWDBOT_ENDPOINT"
CLAWDBOT_TOKEN="$CLAWDBOT_TOKEN"
CLAWDBOT_MODEL="$CLAWDBOT_MODEL"
EOF
echo -e "${GREEN}Saved to $CONFIG_FILE${NC}"

# Step 5: Deploy to robot
echo ""
echo "Step 5: Deploy to Robot"
echo "-----------------------"
read -p "Deploy KayaCan to robot now? [Y/n]: " do_deploy

if [[ ! "$do_deploy" =~ ^[Nn] ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Create .env for robot
    ROBOT_ENV="/tmp/kayacan_robot.env"
    cat > "$ROBOT_ENV" << EOF
# KayaCan Robot Environment
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

    echo "Deploying files to robot..."
    DEST_PATH="/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app"

    # Copy conversation app files
    sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no -r \
        "$SCRIPT_DIR/pollen_app/src/reachy_mini_conversation_app/"* \
        "$ROBOT_USER@$ROBOT_IP:$DEST_PATH/"

    # Copy .env
    sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no \
        "$ROBOT_ENV" "$ROBOT_USER@$ROBOT_IP:$DEST_PATH/.env"

    rm "$ROBOT_ENV"
    echo -e "${GREEN}Deployed successfully!${NC}"

    # Restart app
    echo "Restarting conversation app..."
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$ROBOT_USER@$ROBOT_IP" \
        "sudo fuser -k 7862/tcp 2>/dev/null || true"
    curl -s -X POST "http://$ROBOT_IP:8000/api/apps/restart-current-app" > /dev/null

    echo ""
    echo -e "${GREEN}=========================================="
    echo "  Setup Complete!"
    echo "==========================================${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Start OpenClaw on your Mac:"
    echo "     openclaw serve --host 0.0.0.0 --port 18789"
    echo ""
    echo "  2. Wait ~20 seconds for app to start"
    echo ""
    echo "  3. Get Gradio URL from robot logs:"
    echo "     ssh $ROBOT_USER@$ROBOT_IP 'journalctl -u reachy-mini-launcher -f'"
    echo ""
    echo "  4. Open the https://xxxx.gradio.live URL in browser"
    echo ""
    echo "Quick commands saved to: $CONFIG_FILE"
fi
