---
name: reachy-mini
description: Control Reachy Mini robot via REST API. Use when moving the robot's head, antennas, playing animations, capturing images, text-to-speech, or checking robot status. Triggers on "reachy", "robot", "move head", "wave", "dance", "look at", "say" commands.
---

# Reachy Mini Control

Control Reachy Mini robot at `http://192.168.1.171:8000`.

## Tools

### `reachy_status`
Get daemon and robot status.
```bash
curl -s http://192.168.1.171:8000/api/daemon/status
```

### `reachy_wake_up`
Wake the robot (start daemon + motors).
```bash
curl -s -X POST "http://192.168.1.171:8000/api/daemon/start?wake_up=true"
```

### `reachy_sleep`
Put the robot to sleep.
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/play/goto_sleep
```

### `reachy_move_head`
Move the robot's head to a target position. Uses `/api/move/goto` with smooth interpolation.

**Safety Limits:** pitch ±30°, roll ±30°, yaw ±45°

```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 10, "yaw": 0}, "duration": 1.0}'
```

**Examples:**
- Look up: `"pitch": 20`
- Look down: `"pitch": -20`
- Look left: `"yaw": 30`
- Look right: `"yaw": -30`
- Tilt right: `"roll": 20`
- Nod yes:
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": 15}, "duration": 0.3}'
sleep 0.35
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": -10}, "duration": 0.3}'
sleep 0.35
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": 0}, "duration": 0.3}'
```
- Shake no:
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"yaw": 25}, "duration": 0.25}'
sleep 0.3
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"yaw": -25}, "duration": 0.25}'
sleep 0.3
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"yaw": 0}, "duration": 0.3}'
```

### `reachy_move_antennas`
Move the robot's antennas. Values in degrees.

```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"antennas": [40, 40], "duration": 0.3}'
```

**Examples:**
- Perk up (attention): `"antennas": [60, 60]`
- Droop (sad): `"antennas": [-20, -20]`
- Wiggle (happy): alternate `[40, -40]` and `[-40, 40]`
- Neutral: `"antennas": [0, 0]`

### `reachy_play_emotion`
Play a predefined emotion animation from the HuggingFace emotions library.

```bash
curl -s -X POST http://192.168.1.171:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{emotion_name}
```

**Available emotions:**
cheerful1, happy → cheerful1, sad1, sad2, surprised1, surprised2, fear1, scared1, rage1, furious1, contempt1, disgusted1, frustrated1, irritated1, irritated2, impatient1, impatient2, curious1, thoughtful1, thoughtful2, confused1, uncertain1, shy1, lonely1, tired1, exhausted1, boredom1, boredom2, anxious → anxiety1, proud1, proud2, proud3, grateful1, loving1, welcoming1, welcoming2, helpful1, helpful2, understanding1, understanding2, calming1, serenity1, relief1, relief2, success1, success2, amazed1, enthusiastic1, enthusiastic2, electric1, attentive1, attentive2, inquiring1, inquiring2, inquiring3, indifferent1, resigned1, uncomfortable1, downcast1, lost1, incomprehensible2, laughing1, laughing2, dying1, oops1, oops2, reprimand1, reprimand2, reprimand3, displeased1, displeased2, go_away1, come1, no1, no_excited1, no_sad1, yes1, yes_sad1, sleep1, dance1, dance2, dance3

### `reachy_dance`
Trigger a dance routine from the HuggingFace dances library.

```bash
curl -s -X POST http://192.168.1.171:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/{dance_name}
```

**Available dances:**
side_glance_flick, jackson_square, side_peekaboo, groovy_sway_and_roll, chin_lead, side_to_side_sway, neck_recoil, head_tilt_roll, simple_nod, uh_huh_tilt, interwoven_spirals, pendulum_swing, chicken_peck, yeah_nod, stumble_and_recover, dizzy_spin, grid_snap, polyrhythm_combo, sharp_side_tilt

### `reachy_go_to_zero`
Return to neutral position (head centered, antennas neutral).
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0}, "antennas": [0, 0], "duration": 1.0}'
```

### `reachy_stop`
Immediately stop any running movement.
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/stop
```

### `reachy_motor_status`
Get motor positions and status.
```bash
curl -s http://192.168.1.171:8000/api/motors/status
```

### `reachy_full_state`
Get full robot state (head pose, antennas, body yaw).
```bash
curl -s http://192.168.1.171:8000/api/state/full
```

### `reachy_volume`
Get or set speaker volume.
```bash
# Get current volume
curl -s http://192.168.1.171:8000/api/volume/current

# Set volume (0-100)
curl -s -X POST http://192.168.1.171:8000/api/volume/set \
  -H "Content-Type: application/json" -d '{"volume": 75}'

# Test sound
curl -s -X POST http://192.168.1.171:8000/api/volume/test-sound
```

### `reachy_microphone`
Get or set microphone volume.
```bash
# Get current mic level
curl -s http://192.168.1.171:8000/api/volume/microphone/current

# Set mic level (0-100)
curl -s -X POST http://192.168.1.171:8000/api/volume/microphone/set \
  -H "Content-Type: application/json" -d '{"volume": 80}'
```

## Combined Movements

Head + antennas + body yaw can be moved simultaneously:
```bash
curl -s -X POST http://192.168.1.171:8000/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"pitch": 10, "yaw": 15}, "antennas": [30, 30], "body_yaw": 10, "duration": 1.0, "interpolation": "minjerk"}'
```

Interpolation modes: `minjerk` (smooth, default), `linear`

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

## Dashboard & Admin

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/logs` | GET | View logs |
| `/settings` | GET | Settings page |
| `/api/daemon/status` | GET | Daemon status |
| `/api/daemon/start?wake_up=true` | POST | Start daemon |
| `/api/daemon/stop` | POST | Stop daemon |
| `/api/daemon/restart` | POST | Restart daemon |
| `/api/apps/list-available` | GET | List installable apps |
| `/api/apps/current-app-status` | GET | Current app status |
| `/api/apps/start-app/{name}` | POST | Start an app |
| `/api/apps/stop-current-app` | POST | Stop current app |
| `/update/available` | GET | Check for firmware updates |
| `/update/info` | GET | Current firmware info |
| `/update/start` | POST | Start firmware update |
| `/health-check` | POST | Health check |
| `/wifi/status` | GET | WiFi status |
| `/wifi/scan_and_list` | POST | Scan WiFi networks |

## Notes

- Camera is only accessible via the reachy-mini Python SDK (not REST API)
- The robot must be in `running` state before movement commands work
- Always check daemon status before sending commands
- Use `minjerk` interpolation for natural-looking movements
- Emotions and dances are streamed from HuggingFace datasets on first use
