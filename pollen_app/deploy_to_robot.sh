#!/usr/bin/env bash
# Deploy Clawdbot-modified conversation app to Reachy Mini robot
set -euo pipefail

REACHY_HOST="${REACHY_HOST:-10.0.0.68}"
REACHY_USER="pollen"
REACHY_PASS="root"
REMOTE_APP_DIR="/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src/reachy_mini_conversation_app"

echo "🚀 Deploying Clawdbot integration to Reachy Mini ($REACHY_HOST)..."

# Copy clawdbot_handler.py
echo "📦 Copying clawdbot_handler.py..."
sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/clawdbot_handler.py" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/"

# Copy Honcho tools
echo "📦 Copying Honcho tools..."
sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/tools/honcho_recall.py" \
  "$SRC_DIR/tools/honcho_remember.py" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/tools/"

# Copy modified files
echo "📦 Copying modified core_tools.py..."
sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/tools/core_tools.py" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/tools/"

echo "📦 Copying modified utils.py..."
sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/utils.py" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/"

echo "📦 Copying modified main.py..."
sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/main.py" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/"

# Copy KayaCan profile
echo "📦 Copying KayaCan profile..."
sshpass -p "$REACHY_PASS" ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$REACHY_USER@$REACHY_HOST" "mkdir -p $REMOTE_APP_DIR/profiles/kayacan"

sshpass -p "$REACHY_PASS" scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$SRC_DIR/profiles/kayacan/__init__.py" \
  "$SRC_DIR/profiles/kayacan/instructions.txt" \
  "$SRC_DIR/profiles/kayacan/tools.txt" \
  "$SRC_DIR/profiles/kayacan/voice.txt" \
  "$REACHY_USER@$REACHY_HOST:$REMOTE_APP_DIR/profiles/kayacan/"

# Install dependencies (honcho-ai, pydub)
echo "📦 Installing Python dependencies..."
sshpass -p "$REACHY_PASS" ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$REACHY_USER@$REACHY_HOST" \
  "source /venvs/apps_venv/bin/activate && pip install -q honcho-ai pydub httpx"

# Update .env with Clawdbot config
echo "📦 Updating .env..."
sshpass -p "$REACHY_PASS" ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no \
  "$REACHY_USER@$REACHY_HOST" "cat >> $REMOTE_APP_DIR/.env << 'EOF'

# Clawdbot Mode
USE_CLAWDBOT=true
CLAWDBOT_ENDPOINT=http://10.0.0.234:18789/v1/chat/completions
CLAWDBOT_TOKEN=aefb7d0e1d524d1f460c6942372c65db7df430e40b9ba7c7
CLAWDBOT_MODEL=claude-sonnet-4-20250514

# ElevenLabs TTS
ELEVENLABS_API_KEY=sk_5abb0386037deb5352e6c9d6a333934e27c34feae5d53d92
ELEVENLABS_VOICE_ID=IKne3meq5aSn9XLyUdCD

# Honcho memory
HONCHO_API_KEY=hch-v3-mwm11w7o0rr9snmo7y3p5ox81jxza3656mlqcxuacb3gr282ovzuu6c9vyfk6fml
HONCHO_WORKSPACE_ID=reachy-mini

# Profile
REACHY_MINI_CUSTOM_PROFILE=kayacan
EOF"

echo "✅ Deployment complete!"
echo ""
echo "To start the app with Clawdbot mode:"
echo "  1. Open Reachy dashboard: http://$REACHY_HOST:8000/"
echo "  2. Start conversation app (it will use --clawdbot by default with kayacan profile)"
echo ""
echo "Or start via API:"
echo "  curl -X POST http://$REACHY_HOST:8000/api/apps/start-app/reachy_mini_conversation_app"
