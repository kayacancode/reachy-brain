---
name: reachy-mini
description: Control Reachy Mini robot via REST API. Use when moving the robot's head, antennas, playing animations, capturing images, text-to-speech, or checking robot status. Triggers on "reachy", "robot", "move head", "wave", "dance", "look at", "say" commands.
---

# Reachy Mini Control

Control Reachy Mini robot at `http://192.168.1.171:8000`.

## "Listen" Command (Voice Interaction)

When user says **"listen"**, run this flow:

```bash
# 1. Antennas pop up (alert!)
curl -s -X POST http://192.168.1.171:8000/api/move_antennas -H "Content-Type: application/json" -d '{"left": 60, "right": 60, "duration": 0.3}'

# 2. Record from mic (5 seconds)
curl -s -X POST http://192.168.1.171:8000/api/audio/start_recording
sleep 5
curl -s -X POST http://192.168.1.171:8000/api/audio/stop_recording

# 3. Download recording, transcribe with Whisper, respond

# 4. Generate TTS (use Chatterbox via HuggingFace or macOS say)

# 5. Upload audio and play on Reachy
sshpass -p "root" scp -o StrictHostKeyChecking=no audio.wav pollen@192.168.1.171:/tmp/reachy_mini_testbench/recordings/
curl -s -X POST http://192.168.1.171:8000/api/audio/play/audio.wav

# 6. Return antennas to neutral
curl -s -X POST http://192.168.1.171:8000/api/move_antennas -H "Content-Type: application/json" -d '{"left": 0, "right": 0, "duration": 0.3}'
```

## Quick Animations

```bash
# Antennas pop up (attention!)
curl -s -X POST http://192.168.1.171:8000/api/move_antennas -H "Content-Type: application/json" -d '{"left": 60, "right": 60, "duration": 0.3}'

# Antennas wiggle (happy)
curl -s -X POST http://192.168.1.171:8000/api/move_antennas -H "Content-Type: application/json" -d '{"left": 40, "right": -40, "duration": 0.2}'
sleep 0.25
curl -s -X POST http://192.168.1.171:8000/api/move_antennas -H "Content-Type: application/json" -d '{"left": -40, "right": 40, "duration": 0.2}'

# Head nod (yes)
curl -s -X POST http://192.168.1.171:8000/api/move_head -H "Content-Type: application/json" -d '{"pitch": 15, "duration": 0.3}'
sleep 0.35
curl -s -X POST http://192.168.1.171:8000/api/move_head -H "Content-Type: application/json" -d '{"pitch": -10, "duration": 0.3}'

# Head shake (no)
curl -s -X POST http://192.168.1.171:8000/api/move_head -H "Content-Type: application/json" -d '{"yaw": 25, "duration": 0.25}'
sleep 0.3
curl -s -X POST http://192.168.1.171:8000/api/move_head -H "Content-Type: application/json" -d '{"yaw": -25, "duration": 0.25}'

# Return to neutral
curl -s -X POST http://192.168.1.171:8000/api/go_to_zero
```

## SSH Access

```bash
# User: pollen, Password: root
sshpass -p "root" ssh pollen@192.168.1.171

# Upload audio to Reachy
sshpass -p "root" scp file.wav pollen@192.168.1.171:/tmp/reachy_mini_testbench/recordings/
```

## Chatterbox TTS (via HuggingFace)

```python
from gradio_client import Client

client = Client('ResembleAI/chatterbox-turbo-demo')
result = client.predict(
    text="Hello! I am KayaCan!",
    audio_prompt_path=None,
    temperature=0.8,
    seed_num=42,
    api_name='/generate'
)
# result = path to generated .wav file
```

## Head Movement Limits

- **Pitch**: -40° to 40° (positive = look up)
- **Roll**: -40° to 40° (positive = tilt right)  
- **Yaw**: -180° to 180° (positive = look left)

## API Endpoints Reference

Base: `http://192.168.1.171:8000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Connection status + joint positions |
| `/api/wake_up` | POST | Wake robot |
| `/api/go_to_sleep` | POST | Sleep robot |
| `/api/go_to_zero` | POST | Neutral position |
| `/api/move_head` | POST | `{"pitch":, "roll":, "yaw":, "duration":}` |
| `/api/move_antennas` | POST | `{"left":, "right":, "duration":}` |
| `/api/audio/start_recording` | POST | Start mic recording |
| `/api/audio/stop_recording` | POST | Stop recording, returns filename |
| `/api/audio/download/{file}` | GET | Download recording |
| `/api/audio/play/{file}` | POST | Play audio file |
| `/api/audio/list` | GET | List recordings |
