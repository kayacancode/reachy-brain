# Reachy Brain - Reachy Mini with Claude Brain

Give your [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/) robot a brain powered by Claude. Talk directly to the robot - no browser needed.

## Quick Start

### 1. Start OpenClaw on your Mac

```bash
openclaw gateway
```

### 2. Deploy and run on the robot

```bash
# Deploy the talk script
sshpass -p 'root' scp talk_wireless.py run_talk.sh pollen@ROBOT_IP:/home/pollen/

# SSH in and run
ssh pollen@ROBOT_IP './run_talk.sh'
```

### 3. Talk to Reachy!

The robot will say "Hey! I'm ready to chat." - just start talking.

```
🎤 Listening...
  RMS: 0.051 [█████               ] 🎙️ speech (1)
  RMS: 0.165 [████████████████    ] 🎙️ speech (2)
  RMS: 0.005 [                    ] ... silence (1/2)
  RMS: 0.003 [                    ] ... silence (2/2)
📝 Processing...
You: Hello, how are you?
Reachy: Hey! I'm doing great, thanks for asking!
🔊 Playing audio...
🎤 Listening...
```

## How It Works

```
┌─────────────────┐
│  Robot Mic      │──▶ arecord (stereo 16kHz)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  VAD Detection  │──▶ RMS energy threshold
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Whisper STT    │──▶ OpenAI API
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Claude Brain   │──▶ OpenClaw (Clawdbot)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ElevenLabs TTS │──▶ MP3 audio
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Robot Speaker  │──▶ ffmpeg + aplay
└─────────────────┘
```

## Requirements

### On your Mac
- **OpenClaw** - Claude gateway (`npm install -g openclaw`)
- **sshpass** - For easy SSH (`brew install hudochenkov/sshpass/sshpass`)

### API Keys
- **OpenAI** - For Whisper STT
- **ElevenLabs** - For TTS voice
- **Anthropic** (via OpenClaw) - For Claude brain

## Configuration

Edit `run_talk.sh` on the robot with your keys:

```bash
export OPENAI_API_KEY="sk-..."
export CLAWDBOT_ENDPOINT="http://YOUR_MAC_IP:18789/v1/chat/completions"
export CLAWDBOT_TOKEN="your-openclaw-token"
export ELEVENLABS_API_KEY="sk_..."
export ELEVENLABS_VOICE_ID="REDACTED_VOICE_ID"
```

## Quick Commands

```bash
# Wake up Reachy
./wake.sh

# Put Reachy to sleep
./sleep.sh

# With custom IP
./wake.sh  [ip]
./sleep.sh [ip]
```

## Files

| File | Description |
|------|-------------|
| `talk_wireless.py` | Main conversation loop (runs on robot) |
| `run_talk.sh` | Launcher with API keys (runs on robot) |
| `audio.py` | SDK-based audio (for wired mode) |
| `wake.sh` | Wake up the robot |
| `sleep.sh` | Put robot to sleep |

## Troubleshooting

### "Device or resource busy"
The daemon is using the audio device. Kill it first:
```bash
ssh pollen@ROBOT_IP 'kill -9 $(fuser /dev/snd/* 2>/dev/null | head -1)'
```

### RMS shows 0.000
Audio device name might be wrong. Check with:
```bash
ssh pollen@ROBOT_IP 'arecord -l'
```

### "Chat error" / 500 from Clawdbot
OpenClaw session lock. Clear it:
```bash
rm -f ~/.openclaw/agents/main/sessions/sessions.json.lock
```
Then restart `openclaw gateway`.

### No audio output
Check volume:
```bash
curl http://ROBOT_IP:8000/api/volume/current
curl -X POST http://ROBOT_IP:8000/api/volume/set -d '{"volume": 100}'
```

## Alternative: Gradio Mode

If you prefer browser-based interaction, the Gradio conversation app is also available. See the `/pollen_app` directory for the modified Pollen conversation app with Clawdbot integration.

```bash
# Start conversation app on robot
curl -X POST "http://ROBOT_IP:8000/api/apps/start-app/reachy_mini_conversation_app"

# Get Gradio URL from logs
ssh pollen@ROBOT_IP 'journalctl -u reachy-mini-daemon -f | grep gradio'
```

## License

MIT

## Credits

Built with Claude + OpenClaw
