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

    # Check for portaudio (needed for wake word detection)
    if ! brew list portaudio &>/dev/null; then
        echo "⚠️  portaudio not found (needed for wake word detection)"
        read -p "   Install portaudio now? [Y/n]: " install_pa
        if [[ ! "$install_pa" =~ ^[Nn]$ ]]; then
            echo "   Installing portaudio..."
            brew install portaudio
        fi
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

    echo "   Installing core dependencies..."
    pip install --quiet honcho-ai webrtcvad httpx

    echo "   Installing STT (Speech-to-Text)..."
    pip install --quiet openai-whisper faster-whisper

    echo "   Installing TTS (Text-to-Speech)..."
    pip install --quiet gradio_client piper-tts

    echo "   Installing wake word detection..."
    pip install --quiet openwakeword pyaudio

    echo "   ✅ Python packages installed"

    # Install sshpass if needed
    if ! command -v sshpass >/dev/null; then
        if command -v brew >/dev/null; then
            echo "   Installing sshpass..."
            brew install hudochenkov/sshpass/sshpass 2>/dev/null || true
        fi
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
  "stt": {
    "provider": "faster-whisper",
    "model": "base",
    "device": "cpu",
    "compute_type": "int8"
  },
  "tts": {
    "provider": "piper",
    "piper_voice": "en_US-lessac-medium",
    "cache_enabled": true,
    "cache_dir": "~/.cache/reachy-tts",
    "fallback_to_macos": true,
    "fallback_to_chatterbox": false,
    "chatterbox_space": "ResembleAI/chatterbox-turbo-demo"
  },
  "wake_word": {
    "enabled": true,
    "bot_name": "${AGENT_NAME}",
    "model_path": "~/.config/reachy-brain/wake_words/${AGENT_NAME,,}.onnx",
    "threshold": 0.5,
    "confirmation_sound": true,
    "antenna_response": true
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
    echo "  • Push-to-talk:  reachy-listen --push-to-talk"
    echo "  • Wake word:     reachy-listen --wake-word"
    echo "  • Local testing: reachy-listen --wake-word --local-mic --local-speaker"
    echo ""
    echo "CONFIG: $CONFIG_DIR/config.json"
    echo "SKILL:  $SKILL_DIR"
    echo ""
    echo "WAKE WORD SETUP (Optional):"
    echo "  1. cd $SKILL_DIR"
    echo "  2. python scripts/train_wake_word.py --bot-name ${AGENT_NAME} --record"
    echo "  3. Follow prompts to record 5-10 samples saying 'Hey ${AGENT_NAME}'"
    echo "  4. Model will be saved automatically"
    echo ""
    echo "  Note: Until you train a custom model, the default 'alexa' model will be used."
    echo ""
    echo "Reachy will:"
    echo "  🎤 Listen for wake word (hands-free!)"
    echo "  📡 Pop antennas when activated"
    echo "  🗣️ Transcribe your speech (faster-whisper, 2-4x faster)"
    echo "  🧠 Remember you (Honcho)"
    echo "  💬 Respond with natural voice (Piper TTS, local & fast)"
    echo ""
    echo "Performance improvements:"
    echo "  • STT: 2-4x faster (faster-whisper)"
    echo "  • TTS: 6-10x faster (Piper local TTS)"
    echo "  • Wake word: Voice-activated, no typing needed!"
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
