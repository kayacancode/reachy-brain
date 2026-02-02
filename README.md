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

**Push-to-talk mode** (press ENTER to speak):
```bash
reachy-listen --push-to-talk
```

**Wake word mode** (voice-activated, hands-free):
```bash
reachy-listen --wake-word
```

**Local testing** (test on your machine before deploying to robot):
```bash
reachy-listen --wake-word --local-mic --local-speaker
```

## Wake Word Setup

Enable hands-free voice activation by training a custom wake word model for your bot.

### Quick Start

1. **Train your custom wake word model**:
   ```bash
   cd ~/.clawdbot/skills/reachy-brain
   python scripts/train_wake_word.py --bot-name OpenClaw --record
   ```

2. **Follow the prompts**:
   - Record 5-10 samples of saying "Hey [BotName]"
   - Vary your tone and speed slightly for better accuracy
   - The script will train a model automatically

3. **Test it**:
   ```bash
   reachy-listen --wake-word --local-mic --local-speaker
   ```

4. **Deploy to robot**:
   ```bash
   reachy-listen --wake-word
   ```

### Using Pre-trained Models

If you don't want to train a custom model, you can use pre-trained wake words:

```bash
export WAKE_WORD_MODEL="alexa"  # or "hey_jarvis"
reachy-listen --wake-word
```

Available pre-trained models:
- `alexa` - "Alexa"
- `hey_jarvis` - "Hey Jarvis"

### Wake Word Configuration

Wake word settings in `~/.config/reachy-brain/config.json`:

```json
{
  "wake_word": {
    "enabled": true,
    "bot_name": "OpenClaw",
    "threshold": 0.5,
    "confirmation_sound": true,
    "antenna_response": true
  }
}
```

**Threshold tuning**:
- Lower (0.3-0.4): More sensitive, may have false positives
- Default (0.5): Good balance
- Higher (0.6-0.7): Less sensitive, fewer false positives

## Performance Improvements

This version includes major performance enhancements:

### Speech-to-Text (STT)
- **Provider**: faster-whisper (default)
- **Speed**: 2-4x faster than original Whisper
- **Accuracy**: Identical to original Whisper
- **Example**: 5-second audio: 2-3s → 0.5-1s

Configure in `config.json`:
```json
{
  "stt": {
    "provider": "faster-whisper",
    "model": "base",
    "device": "cpu",
    "compute_type": "int8"
  }
}
```

Models: `tiny`, `base` (recommended), `small`, `medium`, `large`

### Text-to-Speech (TTS)
- **Provider**: Piper TTS (default, local)
- **Speed**: 6-10x faster than Chatterbox
- **Quality**: High-quality neural TTS
- **Latency**: 200-500ms per response
- **Caching**: Common phrases cached for <50ms playback

Configure in `config.json`:
```json
{
  "tts": {
    "provider": "piper",
    "piper_voice": "en_US-lessac-medium",
    "cache_enabled": true,
    "fallback_to_macos": true
  }
}
```

Available voices: `en_US-lessac-medium`, `en_US-ryan-high`, `en_GB-alan-medium`

**Providers**:
- `piper` (recommended): Fast, local, high quality
- `chatterbox`: Cloud-based, highest quality, slower
- `macos`: System voice, fast but robotic

### End-to-End Performance

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| STT | 2-3s | 0.5-1s | 2-4x faster |
| TTS | 3-5s | 0.3-0.5s | 6-10x faster |
| TTS (cached) | 3-5s | <50ms | 60-100x faster |
| **Total latency** | **8-12s** | **3-5s** | **2-3x faster** |

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
