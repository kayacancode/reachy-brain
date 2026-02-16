---
name: reachy-mini
description: Control Reachy Mini robot via REST API. Use when moving the robot's head, antennas, playing animations, capturing images, text-to-speech, or checking robot status. Triggers on "reachy", "robot", "move head", "wave", "dance", "look at", "say" commands.
---

# Reachy Mini Control

Control Reachy Mini robot at `http://10.0.0.68:8000` (daemon) and `http://10.0.0.68:9000` (bridge).
Also reachable via `reachy.local`.

**Full embodiment**: voice, vision, expressions, animations, and persistent memory.

## Voice Agent (Clawdbot + ElevenLabs + Honcho)

Reachy embodies your Clawdbot AI with ElevenLabs voice and Honcho memory.

### Architecture

```
You speak → Reachy's mic → Whisper STT → Clawdbot (your AI) → ElevenLabs TTS → Reachy's speaker
                                              ↓
                                      Honcho Memory (remembers you)
```

### Setup

1. Install dependencies:
```bash
cd ~/clawd/skills/reachy-mini
uv sync
# Or: pip install -e .
```

2. Set environment variables:
```bash
# Required
export OPENAI_API_KEY="sk-..."        # For Whisper STT
export ELEVENLABS_API_KEY="..."       # For TTS

# Optional (has defaults)
export CLAWDBOT_ENDPOINT="http://localhost:18789/v1/chat/completions"
export CLAWDBOT_TOKEN="your-token"
export ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"  # Rachel voice
export HONCHO_API_KEY="..."           # For persistent memory
```

3. Connect Reachy Mini via USB-C.

4. Make sure your Clawdbot is running (OpenClaw on port 18789).

### Run

```bash
cd ~/clawd/skills/reachy-mini
uv run python main.py
```

Press `Ctrl+C` to stop.

### Features

- **Clawdbot Brain**: Your AI personality, not a generic model
- **ElevenLabs Voice**: High-quality, natural-sounding speech
- **Face Tracking**: Reachy follows your face with its gaze
- **Face Recognition**: Identifies who you are and remembers you
- **Honcho Memory**: Persistent memory across conversations
- **Whisper STT**: Accurate speech recognition

### ElevenLabs Voices

Change the voice by setting `ELEVENLABS_VOICE_ID`:
- `21m00Tcm4TlvDq8ikWAM` - Rachel (default)
- `EXAVITQu4vr4xnSDxMaL` - Bella
- `ErXwobaYiN019PkySvjV` - Antoni
- `TxGEqnHWrfWFTfGW9XjX` - Josh
- `pNInz6obpgDQGcFmaJgB` - Adam

Or use your cloned voice ID from ElevenLabs.

## Architecture

Two services on Reachy:
- **Daemon** (port 8000) — built-in Reachy API for movement, emotions, dances, volume
- **Bridge** (port 9000) — our custom service for audio playback and mic recording

### Bridge Setup
Deploy the bridge (only needed once, or after updates):
```bash
~/clawd/skills/reachy-mini/bridge/deploy.sh
```

Check if bridge is running:
```bash
curl -s http://10.0.0.68:9000/status
```

## Quick Reference

### Say Something (TTS → Reachy Speaker)
```bash
# 1. Generate wav on macOS
say -o /tmp/reachy_say.wav --data-format=LEI16@44100 "Hello!"

# 2. Play through bridge
curl -s -X POST http://10.0.0.68:9000/play --data-binary @/tmp/reachy_say.wav
```

### Listen (Record from Reachy Mic)
```bash
# Record 5 seconds (default), returns wav file
curl -s http://10.0.0.68:9000/listen?duration=5 -o /tmp/heard.wav

# Then transcribe locally
whisper /tmp/heard.wav --model tiny --language en --output_format txt --output_dir /tmp
```

### Custom Animations (via Bridge)
```bash
curl -s -X POST http://10.0.0.68:9000/animate/look      # Curious looking around
curl -s -X POST http://10.0.0.68:9000/animate/nod       # Enthusiastic nodding
curl -s -X POST http://10.0.0.68:9000/animate/wiggle    # Excited side-to-side
curl -s -X POST http://10.0.0.68:9000/animate/think     # Thoughtful head tilt
curl -s -X POST http://10.0.0.68:9000/animate/surprise  # Surprised reaction
curl -s -X POST http://10.0.0.68:9000/animate/happy     # Happy bouncing
curl -s -X POST http://10.0.0.68:9000/animate/wave      # Antenna wave greeting
curl -s -X POST http://10.0.0.68:9000/animate/listen    # Attentive pose
curl -s -X POST http://10.0.0.68:9000/animate/alert     # Alert/attention
curl -s -X POST http://10.0.0.68:9000/animate/sad       # Sad expression
curl -s -X POST http://10.0.0.68:9000/animate/reset     # Return to neutral

# List all custom animations
curl -s -X POST http://10.0.0.68:9000/animations
```

### Emotions (Pre-recorded)
```bash
curl -s -X POST http://10.0.0.68:9000/emotion/cheerful1
curl -s -X POST http://10.0.0.68:9000/emotion/welcoming1
curl -s -X POST http://10.0.0.68:9000/emotion/thinking1
```

Available emotions: cheerful1, happy, sad1, sad2, surprised1, surprised2, fear1, scared1, rage1, furious1, contempt1, disgusted1, frustrated1, irritated1, irritated2, impatient1, impatient2, curious1, thoughtful1, thoughtful2, confused1, uncertain1, shy1, lonely1, tired1, exhausted1, boredom1, boredom2, anxiety1, proud1, proud2, proud3, grateful1, loving1, welcoming1, welcoming2, helpful1, helpful2, understanding1, understanding2, calming1, serenity1, relief1, relief2, success1, success2, amazed1, enthusiastic1, enthusiastic2, electric1, attentive1, attentive2, inquiring1, inquiring2, inquiring3, indifferent1, resigned1, uncomfortable1, downcast1, lost1, incomprehensible2, laughing1, laughing2, dying1, oops1, oops2, reprimand1, reprimand2, reprimand3, displeased1, displeased2, go_away1, come1, no1, no_excited1, no_sad1, yes1, yes_sad1, sleep1, dance1, dance2, dance3

### Dances
```bash
curl -s -X POST http://10.0.0.68:9000/dance/jackson_square
curl -s -X POST http://10.0.0.68:9000/dance/groovy_sway_and_roll
```

Available dances: side_glance_flick, jackson_square, side_peekaboo, groovy_sway_and_roll, chin_lead, side_to_side_sway, neck_recoil, head_tilt_roll, simple_nod, uh_huh_tilt, interwoven_spirals, pendulum_swing, chicken_peck, yeah_nod, stumble_and_recover, dizzy_spin, grid_snap, polyrhythm_combo, sharp_side_tilt

### Wake / Sleep / Stop
```bash
curl -s -X POST http://10.0.0.68:9000/wake
curl -s -X POST http://10.0.0.68:9000/sleep
curl -s -X POST http://10.0.0.68:9000/stop
```

### Move Head / Antennas (via bridge → daemon)
```bash
curl -s -X POST http://10.0.0.68:9000/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": 10, "yaw": 15}, "antennas": [30, 30], "duration": 1.0}'
```

### Direct Daemon API (fallback)
If the bridge is down, use the daemon directly:
```bash
# Status
curl -s http://10.0.0.68:8000/api/daemon/status

# Start daemon
curl -s -X POST "http://10.0.0.68:8000/api/daemon/start?wake_up=true"

# Stop daemon
curl -s -X POST "http://10.0.0.68:8000/api/daemon/stop?goto_sleep=true"

# Volume
curl -s http://10.0.0.68:8000/api/volume/current
curl -s -X POST http://10.0.0.68:8000/api/volume/set -H "Content-Type: application/json" -d '{"volume": 75}'

# Emotions/dances (direct)
curl -s -X POST http://10.0.0.68:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{emotion}
curl -s -X POST http://10.0.0.68:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/{dance}
```

## SSH Access
```bash
sshpass -p "root" ssh pollen@10.0.0.68
```

## Bridge Logs
```bash
sshpass -p "root" ssh pollen@10.0.0.68 'cat /tmp/bridge.log'
```

## Custom Animations (Expressive Movements)

Run locally on macOS - these call the daemon's goto API:
```bash
python3 ~/clawd/skills/reachy-mini/animations.py look      # Curious looking around
python3 ~/clawd/skills/reachy-mini/animations.py nod       # Enthusiastic nodding
python3 ~/clawd/skills/reachy-mini/animations.py wiggle    # Excited side-to-side
python3 ~/clawd/skills/reachy-mini/animations.py think     # Thoughtful head tilt
python3 ~/clawd/skills/reachy-mini/animations.py surprise  # Surprised reaction
python3 ~/clawd/skills/reachy-mini/animations.py listen    # Attentive pose
python3 ~/clawd/skills/reachy-mini/animations.py speak     # Subtle speaking movements
python3 ~/clawd/skills/reachy-mini/animations.py happy     # Happy bouncing
python3 ~/clawd/skills/reachy-mini/animations.py wave      # Antenna wave greeting
python3 ~/clawd/skills/reachy-mini/animations.py confused  # Confused expression
python3 ~/clawd/skills/reachy-mini/animations.py sad       # Sad expression
python3 ~/clawd/skills/reachy-mini/animations.py alert     # Alert/attention
python3 ~/clawd/skills/reachy-mini/animations.py idle      # Subtle breathing
python3 ~/clawd/skills/reachy-mini/animations.py reset     # Return to neutral
```

Or use as a Python module:
```python
from animations import look_around, nod_yes, excited_wiggle, play
play("think")  # Play by name
look_around()  # Call directly
```

## Camera / Vision

Take snapshots from Reachy's camera:
```bash
python3 ~/clawd/skills/reachy-mini/camera.py                    # Save to snapshots/
python3 ~/clawd/skills/reachy-mini/camera.py -o photo.jpg       # Save to specific file
python3 ~/clawd/skills/reachy-mini/camera.py --base64           # Get base64 string
python3 ~/clawd/skills/reachy-mini/camera.py --status           # Check camera availability
```

Or use as a module:
```python
from camera import take_snapshot, get_snapshot_base64, get_camera_status
path = take_snapshot()
b64 = get_snapshot_base64()
```

Note: Camera requires either HTTP endpoint on Reachy or SDK with GStreamer support.

## Notes
- Always check daemon status before sending commands
- Bridge must be deployed and running for /play and /listen
- If bridge is down, emotions/dances/wake/sleep still work via direct daemon API
- The robot must be in `running` state before movement commands work
- Camera access depends on Reachy's camera service configuration
- Custom animations run from macOS and call the daemon API directly
