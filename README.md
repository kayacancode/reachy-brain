# KayaCan - Reachy Mini with Claude Brain

Give your [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/) robot a brain powered by Claude, with voice interaction and persistent memory.

## What It Does

- **Voice Input**: Speak to Reachy via browser microphone, transcribed with Whisper
- **Claude Brain**: Powered by Claude via OpenClaw (Clawdbot)
- **Persistent Memory**: Remembers you across conversations with Honcho
- **Natural Voice**: Responds with ElevenLabs TTS through the robot speaker
- **Expressive**: Head movements, antenna pops, dances, and emotions
- **Camera Vision**: Can describe what it sees through its camera

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  Gradio UI   │────▶│   Whisper   │
│   (speak)   │     │  (WebRTC)    │     │   (STT)     │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌──────────────┐     ┌──────▼──────┐
                    │   Honcho     │◀───▶│  Claude     │
                    │  (memory)    │     │ (OpenClaw)  │
                    └──────────────┘     └──────┬──────┘
                                                │
┌─────────────┐     ┌──────────────┐     ┌──────▼──────┐
│   Robot     │◀────│  ElevenLabs  │◀────│   Tools     │
│  Speaker    │     │   (TTS)      │     │ (movement)  │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Components

| Component | Provider | Notes |
|-----------|----------|-------|
| **UI** | Gradio + fastrtc | Browser-based WebRTC audio |
| **STT** | OpenAI Whisper | Cloud API |
| **LLM** | Claude (OpenClaw) | Via Clawdbot proxy |
| **TTS** | ElevenLabs | Plays on robot speaker |
| **Memory** | Honcho | Persistent user context |
| **Robot** | Reachy Mini | REST API + WebRTC |

## Project Structure

```
reachy-mini/
├── pollen_app/                    # Pollen's conversation app (modified)
│   └── src/reachy_mini_conversation_app/
│       ├── main.py                # Entry point, --clawdbot flag
│       ├── clawdbot_handler.py    # Our handler (Whisper→Claude→ElevenLabs)
│       ├── tools/
│       │   ├── core_tools.py      # Tool registry
│       │   ├── honcho_recall.py   # Memory recall tool
│       │   └── honcho_remember.py # Memory save tool
│       └── .env                   # API keys (on robot)
├── reachy_agent/                  # Standalone agent modules
│   ├── clawdbot.py               # OpenClaw HTTP client
│   ├── memory.py                 # Honcho memory wrapper
│   ├── stt.py                    # Whisper transcription
│   └── tts.py                    # ElevenLabs synthesis
└── SKILL.md                      # MCP skill definition
```

## Quick Setup (New Location)

When you move to a new location with Reachy, run the setup script:

```bash
git clone https://github.com/kayacancode/reachy-mini
cd reachy-mini
./setup.sh
```

The script will:
1. **Find your robot** - Auto-discovers on network or enter IP manually
2. **Test connection** - Verifies daemon and SSH access
3. **Configure API keys** - OpenAI, ElevenLabs, Honcho, OpenClaw
4. **Deploy to robot** - Copies all files and .env to robot
5. **Restart app** - Gets everything running

### Quick Commands (After Setup)

```bash
./connect.sh           # Show status and Gradio URL
./connect.sh deploy    # Deploy latest code to robot
./connect.sh restart   # Restart the conversation app
./connect.sh logs      # Stream robot logs
./connect.sh ssh       # SSH into robot
./connect.sh url       # Just print the Gradio URL
```

### Requirements

- **sshpass** - Install with `brew install sshpass` (Mac) or `apt install sshpass` (Linux)
- **curl** - Usually pre-installed
- Robot and computer on same network

---

## Manual Setup

### Prerequisites

- Reachy Mini robot on your network
- OpenClaw running locally (Clawdbot proxy)
- API keys for: OpenAI (Whisper), ElevenLabs, Honcho

### 1. Clone and Install

```bash
git clone https://github.com/kayacancode/reachy-mini
cd reachy-mini
```

### 2. Configure Environment

Create `.env` file with your keys:

```bash
# Clawdbot (OpenClaw endpoint)
CLAWDBOT_ENDPOINT="http://YOUR_MAC_IP:18789/v1/chat/completions"
CLAWDBOT_TOKEN="your-openclaw-token"
CLAWDBOT_MODEL="claude-sonnet-4-20250514"

# OpenAI (for Whisper STT)
OPENAI_API_KEY="sk-..."

# ElevenLabs (TTS)
ELEVENLABS_API_KEY="..."
ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"

# Honcho (memory)
HONCHO_API_KEY="..."
HONCHO_WORKSPACE_ID="reachy-mini"

# Enable Clawdbot mode
USE_CLAWDBOT=true
```

### 3. Deploy to Robot

```bash
# Copy the modified conversation app to robot
sshpass -p "root" scp -r pollen_app/src/reachy_mini_conversation_app/* \
  pollen@REACHY_IP:/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app/

# Restart the app
curl -X POST "http://REACHY_IP:8000/api/apps/restart-current-app"
```

### 4. Start OpenClaw

On your Mac (must be reachable from robot):

```bash
openclaw serve --host 0.0.0.0 --port 18789
```

### 5. Access the UI

The app launches with a Gradio share URL (HTTPS required for browser microphone):

```
https://XXXXXX.gradio.live
```

Check robot logs for the URL:
```bash
ssh pollen@REACHY_IP "journalctl -u reachy-mini-launcher -f"
```

## Usage

1. Open the Gradio share URL in your browser
2. Click "Record" and speak to Reachy
3. Your speech is transcribed, sent to Claude, and the response plays from the robot's speaker

### Voice Commands

- **"What do you see?"** - Uses camera to describe surroundings
- **"Do a happy dance"** - Triggers dance animation
- **"Look up"** - Moves head
- **"What do you remember about me?"** - Recalls memory
- **"Remember that I like coffee"** - Saves to memory

## Available Tools

| Tool | Description |
|------|-------------|
| `camera` | Take a photo and describe it |
| `dance` | Play a dance animation |
| `play_emotion` | Express an emotion |
| `move_head` | Move head (pitch/yaw/roll) |
| `head_tracking` | Enable/disable face tracking |
| `honcho_recall` | Query user memory |
| `honcho_remember` | Save to user memory |

## API Reference

### Reachy Mini Endpoints

```bash
# Daemon Status
curl http://REACHY_IP:8000/api/daemon/status

# Wake/Sleep
curl -X POST "http://REACHY_IP:8000/api/daemon/start?wake_up=true"
curl -X POST http://REACHY_IP:8000/api/move/play/goto_sleep

# Move head
curl -X POST http://REACHY_IP:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": 10, "yaw": 20, "roll": 0}, "duration": 0.5}'

# Antennas
curl -X POST http://REACHY_IP:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"antennas": [45, 45], "duration": 0.3}'

# Play emotion
curl -X POST http://REACHY_IP:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/cheerful1

# Play dance
curl -X POST http://REACHY_IP:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/jackson_square

# Volume control
curl http://REACHY_IP:8000/api/volume/current
curl -X POST http://REACHY_IP:8000/api/volume/set \
  -H "Content-Type: application/json" -d '{"volume": 75}'

# App management
curl http://REACHY_IP:8000/api/apps/list
curl -X POST http://REACHY_IP:8000/api/apps/restart-current-app
```

## ClawdbotHandler Pipeline

The `ClawdbotHandler` class implements the full voice interaction loop:

```python
class ClawdbotHandler(AsyncStreamHandler):
    async def receive(audio_frame):
        # 1. Accumulate audio frames
        # 2. Detect speech (RMS-based VAD)
        # 3. On speech end → process

    async def _process_speech():
        # 1. Whisper STT (16kHz audio → text)
        # 2. Get Honcho memory context
        # 3. Claude LLM (with tools)
        # 4. Execute tool calls
        # 5. ElevenLabs TTS → robot speaker
```

## Troubleshooting

### "Connection refused" to OpenClaw
- Ensure OpenClaw is running: `openclaw serve --host 0.0.0.0 --port 18789`
- Check firewall allows port 18789
- Verify robot can reach your Mac: `ping YOUR_MAC_IP` from robot

### No audio from robot speaker
- Check volume: `curl http://REACHY_IP:8000/api/volume/current`
- Increase volume: `curl -X POST http://REACHY_IP:8000/api/volume/set -d '{"volume": 80}'`

### Microphone not working in browser
- Must use HTTPS (Gradio share URL)
- Allow microphone permission in browser
- Check browser console for errors

### Whisper 401 Unauthorized
- Verify OpenAI API key is valid
- Check `.env` file on robot has correct key

### "Something went wrong" responses
- OpenClaw not running or unreachable
- Check robot logs: `journalctl -u reachy-mini-launcher -f`

### App won't start (port in use)
```bash
# Kill old process and restart
ssh pollen@REACHY_IP "sudo fuser -k 7862/tcp"
curl -X POST http://REACHY_IP:8000/api/apps/restart-current-app
```

## Development

### Local Testing

```bash
cd pollen_app
uv pip install -e ".[clawdbot]"
python -m reachy_mini_conversation_app.main --clawdbot --gradio
```

### Viewing Logs

```bash
# Robot daemon logs
ssh pollen@REACHY_IP "journalctl -u reachy-mini-launcher -f"

# Or via dashboard
open http://REACHY_IP:8000/logs
```

### Updating Code on Robot

```bash
# Single file update
sshpass -p "root" scp clawdbot_handler.py \
  pollen@REACHY_IP:/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app/

# Restart app
curl -X POST http://REACHY_IP:8000/api/apps/restart-current-app
```

## MCP Skill

This project includes an MCP skill for controlling Reachy from Claude Code. See `SKILL.md` for the skill definition and available tools.

## License

MIT

## Credits

Built with Claude by KayaCan

Based on [Pollen Robotics' conversation app](https://huggingface.co/spaces/pollen-robotics/reachy_mini_conversation_app)
