# 🤖 Reachy Brain

Give your [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/) robot a brain powered by Clawdbot, with voice interaction and persistent memory.

## What It Does

- **🎤 Voice Input**: Speak to Reachy, it transcribes with Whisper
- **🧠 Memory**: Remembers you across conversations (Honcho)
- **🗣️ Natural Voice**: Responds with realistic TTS (Chatterbox)
- **🤖 Expressive**: Antennas pop when listening, head moves while talking
- **💬 Smart**: Your Clawdbot agent is the brain

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/your-repo/reachy-brain/main/install.sh | bash
```

Or manually:

```bash
git clone https://github.com/your-repo/reachy-brain
cd reachy-brain
./install.sh
```

## Requirements

| Requirement | Details |
|-------------|---------|
| **Reachy Mini** | On same network, running daemon |
| **Clawdbot** | Installed and configured |
| **Honcho Account** | Free at https://app.honcho.dev |
| **macOS/Linux** | With Python 3.9+ |

## Usage

### From Clawdbot (Telegram, etc.)

Just say **"listen"** to your Clawdbot:

```
You: listen
Bot: 📡 LISTENING...
[speak to Reachy]
Bot: [responds through Reachy's speaker]
```

### Standalone Voice Loop

```bash
reachy-listen --push-to-talk
```

## Configuration

Config lives at `~/.config/reachy-brain/config.json`:

```json
{
  "reachy": {
    "ip": "192.168.1.171",
    "port": 8042,
    "ssh_user": "pollen",
    "ssh_pass": "your-password"
  },
  "honcho": {
    "api_key": "hch-...",
    "workspace": "reachy-brain"
  },
  "agent": {
    "name": "ReachyBot",
    "personality": "A friendly robot assistant"
  }
}
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   You       │────▶│  Reachy Mic  │────▶│   Whisper   │
│  (speak)    │     │   (record)   │     │   (STT)     │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                                                ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Reachy     │◀────│  Chatterbox  │◀────│  Clawdbot   │
│  Speaker    │     │    (TTS)     │     │   + Honcho  │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Components

| Component | Provider | Notes |
|-----------|----------|-------|
| STT | Whisper | Local, free, runs on your machine |
| TTS | Chatterbox | Via HuggingFace Space (free) |
| Memory | Honcho | Cloud API, free tier available |
| Brain | Clawdbot | Your existing agent |
| Robot | Reachy Mini | REST API at port 8042 |

## API Reference

### Reachy Endpoints

```bash
# Status
curl http://REACHY_IP:8042/api/status

# Wake/Sleep
curl -X POST http://REACHY_IP:8042/api/wake_up
curl -X POST http://REACHY_IP:8042/api/go_to_sleep

# Move head
curl -X POST http://REACHY_IP:8042/api/move_head \
  -H "Content-Type: application/json" \
  -d '{"pitch": 10, "yaw": 20, "roll": 0, "duration": 0.5}'

# Antennas
curl -X POST http://REACHY_IP:8042/api/move_antennas \
  -H "Content-Type: application/json" \
  -d '{"left": 45, "right": 45, "duration": 0.3}'

# Record audio
curl -X POST http://REACHY_IP:8042/api/audio/start_recording
sleep 5
curl -X POST http://REACHY_IP:8042/api/audio/stop_recording

# Play audio (file must be in recordings dir)
curl -X POST http://REACHY_IP:8042/api/audio/play/filename.wav
```

### SSH Access

```bash
ssh pollen@REACHY_IP  # password from config

# Audio files location
/tmp/reachy_mini_testbench/recordings/
```

## Troubleshooting

**Can't connect to Reachy**
- Check IP address: `ping REACHY_IP`
- Verify daemon: `curl http://REACHY_IP:8042/api/status`

**Whisper not working**
- Install: `pip install openai-whisper`
- Or: `brew install openai-whisper`

**TTS sounds robotic**
- Chatterbox runs on HuggingFace (may have latency)
- Check: https://huggingface.co/spaces/ResembleAI/chatterbox-turbo-demo

**Memory not working**
- Verify Honcho key at https://app.honcho.dev
- Check workspace exists

## License

MIT

## Credits

Built with 🫧 by KayaCan
