# Reachy Brain 🤖🧠

Give your [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/) a brain powered by [OpenClaw](https://github.com/openclaw/openclaw). Talk to the robot, control Spotify, trigger animations — all by voice.

## What Can It Do?

- **🎤 Voice Conversations** — Talk naturally, powered by Claude via OpenClaw
- **🧠 Persistent Memory** — Remembers you across sessions via [Honcho](https://honcho.dev)
- **🎵 Spotify Control** — "Play some jazz", "skip this song", "what's playing?" — all by voice
- **🎭 Expressive Animations** — 80+ emotions (welcoming, curious, cheerful, dance, etc.)
- **👁️ Face Recognition** — Recognizes and greets known people (optional)
- **📱 Telegram Bridge** — Conversations are relayed to Telegram for logging
- **🔧 Tool Execution** — Extensible tools the AI can call during conversation
- **🗣️ Dynamic Personality** — Loads personality from workspace files (`SOUL.md`, `IDENTITY.md`)

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Reachy Mini │────▶│  Mac Relay   │────▶│   OpenClaw   │
│  (Robot)     │◀────│  Server      │◀────│   Gateway    │
└─────────────┘     └──────────────┘     └──────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼────┐ ┌─────▼─────┐
              │ Spotify   │ │ Telegram  │
              │(AppleScript)│ │  Bot API  │
              └──────────┘ └───────────┘

Robot Pipeline:
  Mic → VAD → STT (Nemotron/Whisper) → Claude (OpenClaw) → ElevenLabs TTS → Speaker
                                            ↕
                                     Honcho Memory
```

## Quick Start

### Prerequisites

- [OpenClaw](https://github.com/openclaw/openclaw) running on your Mac
- Reachy Mini on the same network
- API keys: Anthropic (via OpenClaw), ElevenLabs, and optionally OpenAI for STT

### 1. Configure

```bash
cp .env.example ~/.reachy-brain/.env
# Edit with your API keys
```

### 2. Enable OpenClaw Chat Completions

The robot talks to OpenClaw via the OpenAI-compatible API endpoint:

```bash
# In OpenClaw config, enable:
# gateway.http.endpoints.chatCompletions.enabled: true
```

### 3. Start the Relay Server (Mac)

The relay proxies LLM calls, Spotify control, and Telegram messages:

```bash
RELAY_PORT=18801 OPENCLAW_TOKEN="your-token" python3 relay_server.py
```

### 4. Boot the Robot

```bash
# Wake the daemon
curl -X POST "http://reachy-mini.local:8000/api/daemon/start?wake_up=true"

# Start the audio bridge
ssh pollen@reachy-mini.local 'nohup python3 ~/simple_bridge.py > ~/bridge.log 2>&1 &'

# Start the voice agent
ssh pollen@reachy-mini.local 'source ~/.kayacan/config.env && \
  export OPENCLAW_WORKSPACE=~/clawd && \
  export TELEGRAM_RELAY=http://YOUR_MAC_IP:18801/telegram && \
  nohup python3 talk_wireless.py > ~/talk.log 2>&1 &'
```

Reachy will play a welcoming animation and greet you by voice. Start talking!

## Spotify Control

Spotify is controlled via AppleScript on your Mac — **no Spotify API keys needed**. Just have Spotify open and playing.

Voice commands:
- "Play some Drake"
- "Skip this song" / "Next track"
- "What's playing right now?"
- "Pause the music"
- "Set volume to 50"

The relay server exposes these endpoints:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/spotify/play` | POST | Search and play (`{"query": "...", "type": "track"}`) |
| `/spotify/control` | POST | Playback control (`{"action": "next\|previous\|play\|pause\|shuffle\|volume"}`) |
| `/spotify/status` | GET | Current playback info |

## Animations

Reachy has 80+ expressive animations via the daemon API:

```bash
# Play an emotion
curl -X POST "http://reachy-mini.local:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/cheerful1"

# Available emotions include:
# welcoming, curious, cheerful, laughing, enthusiastic, dance,
# thoughtful, shy, proud, grateful, amazed, confused, sad, and many more
```

## Files

| File | Description |
|------|-------------|
| `talk_wireless.py` | Main voice agent (runs on robot) |
| `tools.py` | AI-callable tools (Spotify, animations, etc.) |
| `simple_bridge.py` | Audio playback bridge (WAV → speaker via dmix) |
| `relay_server.py` | Mac-side relay (LLM proxy, Spotify, Telegram) |
| `vision.py` | Face recognition system |
| `memory.py` | Honcho memory integration |
| `.env.example` | Configuration template |

## Audio Notes

- The Reachy daemon holds exclusive access to the audio device (`hw:0,0`)
- The bridge uses `reachymini_audio_sink` (ALSA dmix) for shared playback
- TTS audio is converted to stereo 16kHz via ffmpeg before playing
- Microphone input uses `reachymini_audio_src` (dsnoop)

## Troubleshooting

### "Transcription error: All connection attempts failed"
STT server is unreachable. Check the `STT_ENDPOINT` in your config — it may be on a different machine than your Mac.

### "No response from OpenClaw"
The `/v1/chat/completions` endpoint isn't enabled or the relay can't reach OpenClaw. Verify:
```bash
curl -X POST http://localhost:18789/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","messages":[{"role":"user","content":"hi"}]}'
```

### No audio output
The bridge may be using the wrong ALSA device. Check:
```bash
aplay -L | grep reachy  # Should show reachymini_audio_sink
curl http://reachy-mini.local:8000/api/volume/current  # Should be 100
curl -X POST http://reachy-mini.local:8000/api/volume/test-sound  # Test beep
```

### "Device or resource busy"
Something else is holding the audio device. Check with:
```bash
fuser /dev/snd/*
```

## Credits

- **[Kaya Jones](https://github.com/kayacancode)** — Original creator
- Built with [OpenClaw](https://github.com/openclaw/openclaw), [Honcho](https://honcho.dev), [ElevenLabs](https://elevenlabs.io), and [Pollen Robotics](https://www.pollen-robotics.com)

## License

MIT
