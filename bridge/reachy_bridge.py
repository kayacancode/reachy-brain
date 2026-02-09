#!/usr/bin/env python3
"""
Reachy Bridge — Cooper's SDK-Native Push Architecture
===================================================

Runs ON Reachy Mini. Uses ReachyMini SDK for continuous listening.
When speech detected, PUSHes audio to macOS server immediately.

Cooper's Push Architecture:
1. Background thread continuously records 1-sec chunks via SDK
2. Local noise gate (0.02 threshold) — only process speech
3. When speech detected, immediately POST to macOS server
4. HTTP server for playback, emotions, control (legacy endpoints)

Adapted from coopergwrenn/clawd-reachy patterns.

Endpoints:
  POST /play        — play wav audio (raw bytes)
  POST /play/base64 — play base64-encoded wav audio
  GET  /listen      — manual recording (legacy compatibility)
  POST /emotion/<name> — play emotion animation
  POST /dance/<name>   — play dance
  POST /animate/<name> — play custom animation (look, nod, wiggle, think, etc.)
  GET  /status      — robot + bridge status
  POST /wake        — wake up robot
  POST /sleep       — put robot to sleep
  POST /stop        — stop current movement
  POST /goto        — move head/antennas
  POST /configure   — set macOS endpoint

Background Thread:
  Continuous SDK recording → noise gate → POST to macOS when speech detected

Usage:
  python3 reachy_bridge.py [--macos-host IP] [--macos-port PORT]

Environment:
  MACOS_HOST=192.168.1.100 (where to POST detected speech)
"""

import sys
import os
import time
import json
import base64
import wave
import io
import threading
import requests
import numpy as np
import argparse
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add the Reachy SDK to path
sys.path.insert(0, '/restore/venvs/mini_daemon/lib/python3.12/site-packages')

REACHY_API = "http://127.0.0.1:8000"
BRIDGE_PORT = 9000

# Custom animations (head movements via goto API)
CUSTOM_ANIMATIONS = {
    "look": [
        {"head_yaw": 0.3, "head_z": 0.01, "antennas": [0.5, 0.3], "duration": 0.4, "sleep": 0.5},
        {"head_yaw": -0.3, "head_z": 0.01, "antennas": [0.3, 0.5], "duration": 0.4, "sleep": 0.5},
        {"head_yaw": 0, "head_z": 0.015, "antennas": [0.6, 0.6], "duration": 0.3, "sleep": 0.3},
    ],
    "nod": [
        {"head_pitch": -0.15, "head_z": 0.02, "antennas": [0.5, 0.5], "duration": 0.2, "sleep": 0.25},
        {"head_pitch": 0.1, "head_z": 0, "antennas": [0.4, 0.4], "duration": 0.2, "sleep": 0.25},
        {"head_pitch": -0.15, "head_z": 0.02, "antennas": [0.5, 0.5], "duration": 0.2, "sleep": 0.25},
        {"head_pitch": 0.1, "head_z": 0, "antennas": [0.4, 0.4], "duration": 0.2, "sleep": 0.25},
        {"head_pitch": 0, "head_z": 0.01, "antennas": [0.5, 0.5], "duration": 0.3, "sleep": 0},
    ],
    "wiggle": [
        {"head_roll": 0.15, "head_z": 0.015, "antennas": [0.8, 0.6], "duration": 0.15, "sleep": 0.2},
        {"head_roll": -0.15, "head_z": 0.015, "antennas": [0.6, 0.8], "duration": 0.15, "sleep": 0.2},
        {"head_roll": 0.15, "head_z": 0.015, "antennas": [0.8, 0.6], "duration": 0.15, "sleep": 0.2},
        {"head_roll": -0.15, "head_z": 0.015, "antennas": [0.6, 0.8], "duration": 0.15, "sleep": 0.2},
        {"head_roll": 0, "head_z": 0.01, "antennas": [0.7, 0.7], "duration": 0.2, "sleep": 0},
    ],
    "think": [
        {"head_roll": 0.2, "head_z": 0.01, "head_yaw": 0.1, "antennas": [0.5, 0.2], "duration": 0.6, "sleep": 0.5},
        {"head_roll": 0.25, "antennas": [0.6, 0.15], "duration": 0.4, "sleep": 1.0},
        {"head_roll": 0, "head_z": 0.01, "head_yaw": 0, "antennas": [0.4, 0.4], "duration": 0.5, "sleep": 0},
    ],
    "surprise": [
        {"head_z": 0.03, "antennas": [1.0, 1.0], "duration": 0.15, "sleep": 0.2},
        {"head_z": 0.015, "antennas": [0.7, 0.7], "duration": 0.3, "sleep": 0.3},
        {"head_z": 0.01, "antennas": [0.4, 0.4], "duration": 0.3, "sleep": 0},
    ],
    "happy": [
        {"head_z": 0.025, "antennas": [0.8, 0.8], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.005, "antennas": [0.6, 0.6], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.025, "antennas": [0.8, 0.8], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.005, "antennas": [0.6, 0.6], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.015, "antennas": [0.7, 0.7], "duration": 0.3, "sleep": 0},
    ],
    "wave": [
        {"head_z": 0.01, "antennas": [0.8, 0.3], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.01, "antennas": [0.3, 0.3], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.01, "antennas": [0.8, 0.3], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.01, "antennas": [0.3, 0.8], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.01, "antennas": [0.3, 0.3], "duration": 0.2, "sleep": 0.25},
        {"head_z": 0.015, "antennas": [0.6, 0.6], "duration": 0.3, "sleep": 0},
    ],
    "listen": [
        {"head_z": 0.01, "head_pitch": -0.05, "head_yaw": 0.05, "antennas": [0.5, 0.5], "duration": 0.4, "sleep": 0},
    ],
    "alert": [
        {"head_z": 0.02, "head_pitch": -0.1, "antennas": [0.7, 0.7], "duration": 0.3, "sleep": 0},
    ],
    "sad": [
        {"head_z": -0.01, "head_pitch": 0.1, "antennas": [0.1, 0.1], "duration": 0.8, "sleep": 0},
    ],
    "reset": [
        {"head_z": 0.01, "head_roll": 0, "head_pitch": 0, "head_yaw": 0, "antennas": [0.4, 0.4], "duration": 0.5, "sleep": 0},
    ],
}

# Cooper's settings
CHUNK_DURATION = 1.0  # 1-second chunks for fast detection
NOISE_THRESHOLD = 0.02  # Cooper's noise gate threshold
SILENCE_CHUNKS_TO_TRIGGER = 2  # Buffer speech chunks until this many silent chunks

# Global state
robot = None
macos_host = None
macos_port = 8888  # Default port for macOS voice server
listening_thread = None
listening_active = False

def init_robot():
    """Initialize ReachyMini SDK connection using Cooper's pattern."""
    global robot
    from reachy_mini import ReachyMini
    print("🤖 Connecting to ReachyMini SDK...", flush=True)
    robot = ReachyMini(media_backend="default")
    print("✅ ReachyMini SDK connected!", flush=True)

def get_default_macos_host():
    """Get the first non-localhost IP to use as default macOS host."""
    try:
        # Connect to a remote address to get our local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        # Assume macOS is on same subnet, common gateway IP
        parts = local_ip.split('.')
        return f"{parts[0]}.{parts[1]}.{parts[2]}.1"  # .1 is common gateway
    except:
        return "192.168.1.1"  # fallback

def record_chunk_sdk():
    """Record 1-second chunk using Cooper's SDK pattern."""
    samples = []
    robot.media.start_recording()
    start = time.time()
    while time.time() - start < CHUNK_DURATION:
        s = robot.media.get_audio_sample()
        if s is not None and len(s) > 0:
            samples.append(s)
        time.sleep(0.05)  # Cooper's 50ms sleep
    robot.media.stop_recording()

    if not samples:
        return None, 0.0

    # Cooper's pattern: concatenate samples
    audio = np.concatenate(samples)
    mono = audio[:, 0] if len(audio.shape) > 1 else audio
    
    # Check raw signal level for noise gate
    peak_level = float(np.max(np.abs(mono)))
    
    # Convert to wav bytes
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes((mono * 32767).astype(np.int16).tobytes())
    buf.seek(0)
    
    return buf.read(), peak_level

def send_audio_to_macos(wav_chunks):
    """Send accumulated speech chunks to macOS server."""
    if not macos_host or not wav_chunks:
        return
    
    # Concatenate chunks - simple approach for now
    # In production, you'd properly merge WAV headers
    all_frames = b''
    for wav_bytes in wav_chunks:
        # Extract frames from each WAV (skip header)
        if len(wav_bytes) > 44:  # Standard WAV header is 44 bytes
            all_frames += wav_bytes[44:]
    
    # Create combined WAV
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(all_frames)
    buf.seek(0)
    combined_wav = buf.read()
    
    try:
        url = f"http://{macos_host}:{macos_port}/audio"
        print(f"🚀 Pushing {len(wav_chunks)} chunks ({len(combined_wav)} bytes) to {url}", flush=True)
        
        response = requests.post(
            url,
            data=combined_wav,
            headers={'Content-Type': 'audio/wav'},
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✅ macOS received audio successfully", flush=True)
        else:
            print(f"❌ macOS rejected audio: {response.status_code}", flush=True)
            
    except Exception as e:
        print(f"❌ Failed to send to macOS: {e}", flush=True)

def continuous_listener():
    """Cooper's continuous listening loop - runs in background thread."""
    global listening_active
    
    print(f"🎤 Starting continuous listener (threshold: {NOISE_THRESHOLD})...", flush=True)
    
    accumulated_chunks = []
    silence_counter = 0
    
    while listening_active:
        try:
            # Record one chunk using Cooper's pattern
            wav_chunk, peak_level = record_chunk_sdk()
            if wav_chunk is None:
                time.sleep(0.1)
                continue
            
            # Cooper's noise gate
            is_speech = peak_level > NOISE_THRESHOLD
            
            if is_speech:
                # Speech detected - accumulate
                print(f"🎤 Speech: peak={peak_level:.4f}", flush=True)
                accumulated_chunks.append(wav_chunk)
                silence_counter = 0
            else:
                # Silence detected
                print(f"🔇 Silence: peak={peak_level:.4f}", flush=True)
                if accumulated_chunks:  # We have speech waiting
                    silence_counter += 1
                    if silence_counter >= SILENCE_CHUNKS_TO_TRIGGER:
                        # End of speech - send to macOS
                        threading.Thread(
                            target=send_audio_to_macos,
                            args=(accumulated_chunks.copy(),),
                            daemon=True
                        ).start()
                        
                        # Reset for next speech
                        accumulated_chunks.clear()
                        silence_counter = 0
                        
        except Exception as e:
            print(f"❌ Listener error: {e}", flush=True)
            time.sleep(1)  # Brief pause on error
    
    print("🛑 Continuous listener stopped", flush=True)

def start_listening():
    """Start background listening thread."""
    global listening_thread, listening_active
    
    if not macos_host:
        print("❌ Cannot start listening: macOS host not configured", flush=True)
        return False
    
    if listening_thread and listening_thread.is_alive():
        print("🎤 Listener already running", flush=True)
        return True
    
    listening_active = True
    listening_thread = threading.Thread(target=continuous_listener, daemon=True)
    listening_thread.start()
    print("✅ Background listening started", flush=True)
    return True

def stop_listening():
    """Stop background listening thread."""
    global listening_active
    listening_active = False
    print("🛑 Stopping background listening...", flush=True)

def play_wav_data(wav_bytes):
    """Play wav audio using Cooper's SDK pattern."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        sr = wf.getframerate()
        nc = wf.getnchannels()
        # Cooper's playback pattern
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if nc == 1:
            audio = np.column_stack([audio, audio])  # Convert to stereo

    robot.media.start_playing()
    robot.media.push_audio_sample(audio)
    time.sleep(len(audio) / sr + 0.5)  # Cooper's timing
    robot.media.stop_playing()

def reachy_api(method, endpoint, data=None):
    """Call Reachy daemon API."""
    url = f"{REACHY_API}{endpoint}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json=data, timeout=10)
        return r.json() if r.text else {}
    except Exception as e:
        return {"error": str(e)}


def play_custom_animation(name):
    """Play a custom animation sequence using goto API."""
    if name not in CUSTOM_ANIMATIONS:
        return {"error": f"Unknown animation: {name}", "available": list(CUSTOM_ANIMATIONS.keys())}

    steps = CUSTOM_ANIMATIONS[name]
    print(f"Playing custom animation: {name} ({len(steps)} steps)", flush=True)

    for step in steps:
        # Build goto payload
        head_pose = {
            "x": 0,
            "y": 0,
            "z": step.get("head_z", 0),
            "roll": step.get("head_roll", 0),
            "pitch": step.get("head_pitch", 0),
            "yaw": step.get("head_yaw", 0),
        }
        payload = {
            "head_pose": head_pose,
            "antennas_position": step.get("antennas", [0.4, 0.4]),
            "duration": step.get("duration", 0.5),
        }

        reachy_api("POST", "/api/move/goto", payload)
        sleep_time = step.get("sleep", 0)
        if sleep_time > 0:
            time.sleep(sleep_time)

    return {"status": "ok", "animation": name, "steps": len(steps)}

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}", flush=True)

    def _respond(self, code, body):
        self.send_response(code)
        if isinstance(body, bytes):
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(body)))
        else:
            self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if isinstance(body, bytes):
            self.wfile.write(body)
        else:
            self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        if self.path == '/status':
            daemon = reachy_api("GET", "/api/daemon/status")
            self._respond(200, {
                "bridge": "Cooper's SDK Architecture",
                "port": BRIDGE_PORT,
                "sdk": "ReachyMini" if robot else "not connected",
                "daemon": daemon,
                "continuous_listening": listening_active,
                "macos_host": macos_host,
                "macos_port": macos_port,
                "noise_threshold": NOISE_THRESHOLD,
                "chunk_duration": CHUNK_DURATION
            })

        elif self.path.startswith('/listen'):
            # Legacy compatibility for manual recording
            duration = 5
            if '?' in self.path:
                params = dict(p.split('=') for p in self.path.split('?')[1].split('&') if '=' in p)
                duration = float(params.get('duration', 5))
            try:
                # Use multiple chunks for longer recordings
                chunks = int(duration / CHUNK_DURATION) or 1
                wav_data, peak = record_chunk_sdk()
                print(f"🎤 Manual recording: {duration}s, peak={peak:.4f}", flush=True)
                if wav_data:
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/wav')
                    self.send_header('Content-Length', str(len(wav_data)))
                    self.send_header('X-Raw-Peak', f"{peak:.6f}")
                    self.end_headers()
                    self.wfile.write(wav_data)
                else:
                    self._respond(500, {"error": "recording failed"})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))

        if self.path == '/play':
            # Cooper's playback endpoint
            try:
                wav_data = self.rfile.read(content_length)
                print(f"🔊 Playing {len(wav_data)} bytes...", flush=True)
                play_wav_data(wav_data)
                self._respond(200, {"status": "ok", "played_bytes": len(wav_data)})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == '/play/base64':
            try:
                body = json.loads(self.rfile.read(content_length))
                wav_data = base64.b64decode(body['audio'])
                print(f"🔊 Playing {len(wav_data)} bytes (b64)...", flush=True)
                play_wav_data(wav_data)
                self._respond(200, {"status": "ok"})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == '/configure':
            # Set macOS endpoint and start listening
            try:
                global macos_host, macos_port
                body = json.loads(self.rfile.read(content_length))
                macos_host = body.get('host', macos_host)
                macos_port = body.get('port', macos_port)
                
                print(f"🎯 Configured macOS endpoint: {macos_host}:{macos_port}", flush=True)
                
                # Auto-start listening
                if start_listening():
                    self._respond(200, {
                        "status": "configured", 
                        "host": macos_host, 
                        "port": macos_port,
                        "listening": True
                    })
                else:
                    self._respond(500, {"error": "failed to start listening"})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path.startswith('/animate/'):
            # Custom animations (look, nod, wiggle, think, surprise, etc.)
            anim_name = self.path.split('/animate/')[-1]
            result = play_custom_animation(anim_name)
            self._respond(200, result)

        elif self.path == '/animations':
            # List available custom animations
            self._respond(200, {"animations": list(CUSTOM_ANIMATIONS.keys())})

        elif self.path.startswith('/emotion/'):
            emotion = self.path.split('/emotion/')[-1]
            result = reachy_api("POST",
                f"/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{emotion}")
            self._respond(200, result)

        elif self.path.startswith('/dance/'):
            dance = self.path.split('/dance/')[-1]
            result = reachy_api("POST",
                f"/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/{dance}")
            self._respond(200, result)

        elif self.path == '/wake':
            result = reachy_api("POST", "/api/move/play/wake_up")
            self._respond(200, result)

        elif self.path == '/sleep':
            result = reachy_api("POST", "/api/move/play/goto_sleep")
            self._respond(200, result)

        elif self.path == '/stop':
            result = reachy_api("POST", "/api/move/stop")
            self._respond(200, result)

        elif self.path == '/goto':
            try:
                body = json.loads(self.rfile.read(content_length))
                result = reachy_api("POST", "/api/move/goto", body)
                self._respond(200, result)
            except Exception as e:
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "not found"})

def main():
    """Main entry point."""
    global macos_host, macos_port
    
    parser = argparse.ArgumentParser(description="Reachy Bridge - Cooper's SDK Architecture")
    parser.add_argument('--macos-host', default=os.environ.get('MACOS_HOST'),
                       help='macOS host IP (default: auto-detect or env MACOS_HOST)')
    parser.add_argument('--macos-port', type=int, default=8888,
                       help='macOS voice server port (default: 8888)')
    parser.add_argument('--no-listen', action='store_true',
                       help='Disable continuous listening (use polling mode only)')
    args = parser.parse_args()
    
    # Initialize SDK
    init_robot()
    
    # Configure macOS endpoint
    if args.macos_host:
        macos_host = args.macos_host
    else:
        macos_host = get_default_macos_host()
        print(f"🎯 Auto-detected macOS host: {macos_host}", flush=True)
    
    macos_port = args.macos_port
    
    print(f"🌉 Starting Reachy Bridge on port {BRIDGE_PORT}")
    print(f"🎯 Will push speech to: {macos_host}:{macos_port}")
    print(f"🎚️  Noise threshold: {NOISE_THRESHOLD}")
    print(f"⏱️  Chunk duration: {CHUNK_DURATION}s")
    print(f"🔇 Silence trigger: {SILENCE_CHUNKS_TO_TRIGGER} chunks")
    
    # Auto-start listening if macOS host is configured (and not disabled)
    if macos_host and not args.no_listen:
        start_listening()
    elif args.no_listen:
        print("🔇 Continuous listening disabled (polling mode only)", flush=True)
    
    try:
        HTTPServer(('0.0.0.0', BRIDGE_PORT), BridgeHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...", flush=True)
        stop_listening()

if __name__ == "__main__":
    main()