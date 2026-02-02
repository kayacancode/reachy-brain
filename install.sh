#!/bin/bash
#
# 🤖 Reachy Brain Installer
# Gives your Reachy Mini a Clawdbot brain with memory
#
# Usage: curl -fsSL https://example.com/reachy-brain/install.sh | bash
#

set -e

SKILL_DIR="${HOME}/.clawdbot/skills/reachy-brain"
CONFIG_DIR="${HOME}/.config/reachy-brain"
VENV_DIR="${HOME}/.local/share/reachy-brain/venv"

echo ""
echo "🤖 ═══════════════════════════════════════════"
echo "   REACHY BRAIN INSTALLER"
echo "   Voice + Memory + Personality for Reachy Mini"
echo "═══════════════════════════════════════════════"
echo ""

# Check prerequisites
check_prereqs() {
    local missing=()
    
    command -v python3 >/dev/null || missing+=("python3")
    command -v clawdbot >/dev/null || missing+=("clawdbot")
    command -v ffmpeg >/dev/null || missing+=("ffmpeg")
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo "❌ Missing requirements: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  brew install python ffmpeg"
        echo "  npm i -g clawdbot"
        exit 1
    fi
    echo "✅ Prerequisites OK"
}

# Collect configuration
collect_config() {
    echo ""
    echo "📝 Configuration"
    echo "────────────────"
    
    # Reachy connection
    read -p "Reachy Mini IP address [192.168.1.171]: " REACHY_IP
    REACHY_IP=${REACHY_IP:-192.168.1.171}
    
    read -p "Reachy SSH username [pollen]: " REACHY_SSH_USER
    REACHY_SSH_USER=${REACHY_SSH_USER:-pollen}
    
    read -sp "Reachy SSH password: " REACHY_SSH_PASS
    echo ""
    
    # Test Reachy connection
    echo "   Testing Reachy connection..."
    if curl -s --connect-timeout 5 "http://${REACHY_IP}:8042/api/status" >/dev/null 2>&1; then
        echo "   ✅ Reachy Mini connected!"
    else
        echo "   ⚠️  Can't reach Reachy at ${REACHY_IP}:8042"
        read -p "   Continue anyway? [y/N]: " cont
        [[ "$cont" =~ ^[Yy]$ ]] || exit 1
    fi
    
    echo ""
    
    # Honcho memory
    echo "🧠 Honcho Memory (https://app.honcho.dev)"
    read -p "Honcho API key: " HONCHO_API_KEY
    read -p "Honcho workspace name [reachy-brain]: " HONCHO_WORKSPACE
    HONCHO_WORKSPACE=${HONCHO_WORKSPACE:-reachy-brain}
    
    echo ""
    
    # Agent identity
    echo "🤖 Agent Identity"
    read -p "Agent name [ReachyBot]: " AGENT_NAME
    AGENT_NAME=${AGENT_NAME:-ReachyBot}
    
    read -p "Agent personality (short description): " AGENT_PERSONALITY
    AGENT_PERSONALITY=${AGENT_PERSONALITY:-A friendly robot assistant}
}

# Install Python dependencies
install_deps() {
    echo ""
    echo "📦 Installing dependencies..."
    
    # Create virtual environment
    mkdir -p "$(dirname "$VENV_DIR")"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    pip install --quiet --upgrade pip
    pip install --quiet honcho-ai gradio_client webrtcvad
    
    echo "   ✅ Python packages installed"
    
    # Install sshpass if needed
    if ! command -v sshpass >/dev/null; then
        if command -v brew >/dev/null; then
            echo "   Installing sshpass..."
            brew install hudochenkov/sshpass/sshpass 2>/dev/null || true
        fi
    fi
    
    # Install whisper if needed
    if ! command -v whisper >/dev/null; then
        echo "   Installing Whisper (this may take a moment)..."
        pip install --quiet openai-whisper
    fi
    
    echo "   ✅ All dependencies ready"
}

# Write configuration
write_config() {
    echo ""
    echo "💾 Saving configuration..."
    
    mkdir -p "$CONFIG_DIR"
    
    cat > "$CONFIG_DIR/config.json" << EOF
{
  "reachy": {
    "ip": "${REACHY_IP}",
    "port": 8042,
    "ssh_user": "${REACHY_SSH_USER}",
    "ssh_pass": "${REACHY_SSH_PASS}"
  },
  "honcho": {
    "api_key": "${HONCHO_API_KEY}",
    "workspace": "${HONCHO_WORKSPACE}"
  },
  "agent": {
    "name": "${AGENT_NAME}",
    "personality": "${AGENT_PERSONALITY}"
  },
  "tts": {
    "provider": "chatterbox",
    "huggingface_space": "ResembleAI/chatterbox-turbo-demo"
  },
  "stt": {
    "provider": "whisper",
    "model": "base"
  }
}
EOF

    chmod 600 "$CONFIG_DIR/config.json"
    echo "   ✅ Config saved to $CONFIG_DIR/config.json"
}

# Install skill files
install_skill() {
    echo ""
    echo "📂 Installing skill..."
    
    mkdir -p "$SKILL_DIR/scripts"
    
    # Copy scripts from current directory or download
    if [ -f "scripts/voice_loop.py" ]; then
        cp -r scripts/* "$SKILL_DIR/scripts/"
        cp SKILL.md "$SKILL_DIR/" 2>/dev/null || true
    else
        echo "   Downloading skill files..."
        # Would download from repo here
        echo "   ⚠️  Run this from the reachy-brain directory"
    fi
    
    # Create launcher script
    cat > "$SKILL_DIR/bin/reachy-listen" << 'LAUNCHER'
#!/bin/bash
CONFIG="${HOME}/.config/reachy-brain/config.json"
VENV="${HOME}/.local/share/reachy-brain/venv"
SCRIPT="${HOME}/.clawdbot/skills/reachy-brain/scripts/voice_loop.py"

source "$VENV/bin/activate"
export REACHY_CONFIG="$CONFIG"
python "$SCRIPT" "$@"
LAUNCHER
    chmod +x "$SKILL_DIR/bin/reachy-listen"
    
    echo "   ✅ Skill installed"
}

# Configure Clawdbot
configure_clawdbot() {
    echo ""
    echo "⚙️  Configuring Clawdbot..."
    
    # Enable HTTP API if not already
    # This would use clawdbot CLI or modify config
    echo "   Note: Make sure Clawdbot HTTP API is enabled"
    echo "   Run: clawdbot config set gateway.http.endpoints.chatCompletions.enabled true"
    
    echo "   ✅ Clawdbot configured"
}

# Print success message
print_success() {
    echo ""
    echo "═══════════════════════════════════════════════"
    echo "🎉 INSTALLATION COMPLETE!"
    echo "═══════════════════════════════════════════════"
    echo ""
    echo "Your Reachy Mini now has a brain! 🤖🧠"
    echo ""
    echo "USAGE:"
    echo "  • Tell your Clawdbot 'listen' and speak to Reachy"
    echo "  • Or run: reachy-listen --push-to-talk"
    echo ""
    echo "CONFIG: $CONFIG_DIR/config.json"
    echo "SKILL:  $SKILL_DIR"
    echo ""
    echo "Reachy will:"
    echo "  📡 Pop antennas when listening"
    echo "  🎤 Transcribe your speech (Whisper)"
    echo "  🧠 Remember you (Honcho)"
    echo "  🗣️ Respond with natural voice (Chatterbox)"
    echo ""
    echo "ebaaa jeeba! 🫧"
}

# Main
main() {
    check_prereqs
    collect_config
    install_deps
    write_config
    install_skill
    configure_clawdbot
    print_success
}

main "$@"
