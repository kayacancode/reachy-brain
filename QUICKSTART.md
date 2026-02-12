# Reachy Mini - Quick Start

## Full Startup

### 1. On Your Mac - Start OpenClaw gateway (keep running)
```bash
openclaw gateway
```

### 2. On Your Mac - Wake up the robot
```bash
curl -X POST "http://192.168.23.66:8000/api/daemon/start?wake_up=true"
```

### 3. SSH to Robot
```bash
ssh pollen@192.168.23.66  # password: root
```

### 4. On Robot - Start camera server (background)
```bash
nohup python3 ~/camera_server.py > ~/camera.log 2>&1 &
```

### 5. On Robot - Start talk mode
```bash
./run_talk.sh              # Default workspace: openclaw
./run_talk.sh myworkspace  # Custom workspace
```

---

## One-Liner (on robot)

Start everything at once:
```bash
pkill -f camera_server; nohup python3 ~/camera_server.py > ~/camera.log 2>&1 & sleep 2 && ./run_talk.sh
```

---

## Face Enrollment

Enroll your face for personalized Honcho memory:
```bash
python3 ~/enroll_face.py --name kaya
python3 ~/enroll_face.py --list    # List enrolled users
python3 ~/enroll_face.py --delete kaya  # Remove a user
```

---

## Status Checks

```bash
curl http://192.168.23.66:8000/api/daemon/status  # Robot daemon
curl http://192.168.23.66:9001/status              # Camera server
```

---

## Stop Everything

Kill specific processes:
```bash
pkill -f camera_server.py
pkill -f talk_wireless.py
pkill -f reachy_bridge.py
```

Kill all (nuclear option):
```bash
pkill -f python3
```

---

## Environment

Set these in `~/.kayacan/config.env`:
```bash
ROBOT_IP="192.168.23.66"
OPENAI_API_KEY="sk-..."
ELEVENLABS_API_KEY="sk_..."
HONCHO_API_KEY="hch-..."
CLAWDBOT_ENDPOINT="http://YOUR_MAC_IP:18789/v1/chat/completions"
CLAWDBOT_TOKEN="your-token"
```
