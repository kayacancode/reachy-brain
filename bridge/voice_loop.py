#!/usr/bin/env python3
"""
Voice Loop — Cooper's Push Architecture
======================================

Runs on macOS. HTTP server that receives speech from Reachy bridge, then:
  1. Transcribe with OpenAI Whisper API
  2. Send to AI via OpenClaw chat completions API
  3. Generate speech with OpenAI TTS
  4. POST wav back to Reachy bridge /play

Cooper's Push Architecture:
- Reachy bridge continuously listens with noise gate
- When speech detected, bridge POSTs audio to this server's /audio endpoint
- This server processes and responds back to bridge

Usage:
  export OPENAI_API_KEY=sk-...
  python3 voice_loop.py [--port 8888] [--reachy-bridge http://192.168.1.171:9000]

Environment Variables:
  OPENAI_API_KEY=sk-...           # Required
  OPENCLAW_API=http://localhost:18789
  OPENCLAW_TOKEN=...              # From OpenClaw config
  OPENAI_TTS_VOICE=shimmer        # nova, shimmer, alloy, fable
  REACHY_BRIDGE=http://192.168.1.171:9000
"""

import os
import sys
import json
import time
import requests
import tempfile
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
REACHY_BRIDGE = os.environ.get("REACHY_BRIDGE", "http://192.168.1.171:9000")
OPENCLAW_API = os.environ.get("OPENCLAW_API", "http://localhost:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "REDACTED_CLAWDBOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "shimmer")

# Server settings
VOICE_SERVER_PORT = 8888

def log(msg):
    """Log with timestamp."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def transcribe_audio(wav_bytes):
    """Transcribe audio using OpenAI Whisper API."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            f.flush()
            
            with open(f.name, "rb") as audio_file:
                resp = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": ("audio.wav", audio_file, "audio/wav")},
                    data={"model": "whisper-1", "language": "en"},
                    timeout=15,
                )
            
            os.unlink(f.name)  # Clean up temp file
            
            if resp.ok:
                result = resp.json().get("text", "").strip()
                log(f"👂 Transcribed: \"{result}\"")
                return result
            else:
                log(f"❌ Whisper error: {resp.status_code} {resp.text}")
                return ""
                
    except Exception as e:
        log(f"❌ Transcription failed: {e}")
        return ""

def get_ai_response(text):
    """Get response via OpenClaw chat completions."""
    try:
        resp = requests.post(
            f"{OPENCLAW_API}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENCLAW_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "default",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"You are {os.environ.get('AGENT_NAME', 'Reachy')} speaking through a Reachy Mini robot. "
                            "Keep responses SHORT — 1-2 sentences max. "
                            "Be natural, conversational, warm. "
                            "You're physically present in the room talking to someone. "
                            "Don't use emojis or markdown — this will be spoken aloud."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "max_tokens": 150,
            },
            timeout=30,
        )
        
        if resp.ok:
            data = resp.json()
            response = data["choices"][0]["message"]["content"].strip()
            log(f"💬 AI Response: \"{response}\"")
            return response
        else:
            log(f"❌ OpenClaw error: {resp.status_code} {resp.text}")
            return "Sorry, I didn't catch that."
            
    except Exception as e:
        log(f"❌ AI response failed: {e}")
        return "Sorry, I had a technical issue."

def generate_speech(text):
    """Convert text to speech using OpenAI TTS."""
    try:
        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": OPENAI_TTS_VOICE,
                "response_format": "wav",
            },
            timeout=15,
        )
        
        if resp.ok:
            log(f"🔊 Generated TTS ({len(resp.content)} bytes)")
            return resp.content
        else:
            log(f"❌ TTS error: {resp.status_code} {resp.text}")
            return None
            
    except Exception as e:
        log(f"❌ TTS failed: {e}")
        return None

def send_to_reachy(wav_bytes):
    """Send audio to Reachy bridge for playback."""
    try:
        resp = requests.post(
            f"{REACHY_BRIDGE}/play",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            timeout=30,
        )
        
        if resp.ok:
            log(f"✅ Sent to Reachy ({len(wav_bytes)} bytes)")
            return True
        else:
            log(f"❌ Reachy playback error: {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Failed to send to Reachy: {e}")
        return False

def trigger_emotion(emotion):
    """Trigger emotion animation on Reachy (non-blocking)."""
    def _trigger():
        try:
            requests.post(f"{REACHY_BRIDGE}/emotion/{emotion}", timeout=5)
        except:
            pass  # Non-critical
    threading.Thread(target=_trigger, daemon=True).start()

def process_audio(wav_bytes):
    """Process received audio through the full pipeline."""
    log(f"🎤 Processing audio ({len(wav_bytes)} bytes)")
    
    # Show thinking animation
    trigger_emotion("thoughtful1")
    
    # 1. Transcribe
    text = transcribe_audio(wav_bytes)
    if not text or len(text.strip()) < 2:
        log("🔇 No meaningful text transcribed")
        trigger_emotion("attentive1")
        return
    
    # 2. Get AI response
    response = get_ai_response(text)
    
    # 3. Generate speech
    trigger_emotion("welcoming1")
    speech_bytes = generate_speech(response)
    if not speech_bytes:
        return
    
    # 4. Send to Reachy
    send_to_reachy(speech_bytes)
    
    # 5. Back to listening pose
    trigger_emotion("attentive1")
    log("")  # Blank line for readability

class VoiceServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default request logging
        pass
    
    def do_POST(self):
        if self.path == '/audio':
            # Receive audio from Reachy bridge
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                return
            
            wav_bytes = self.rfile.read(content_length)
            
            # Process in background thread to return quickly
            threading.Thread(
                target=process_audio, 
                args=(wav_bytes,), 
                daemon=True
            ).start()
            
            # Quick response to bridge
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received"}).encode())
            
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            status = {
                "service": "Voice Loop - Cooper's Push Architecture",
                "reachy_bridge": REACHY_BRIDGE,
                "openai_configured": bool(OPENAI_API_KEY),
                "tts_voice": OPENAI_TTS_VOICE,
                "openclaw_api": OPENCLAW_API
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

def configure_bridge(bridge_url, voice_server_port):
    """Configure the Reachy bridge to push audio to this server."""
    try:
        # Get local IP for bridge to reach us
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        config = {
            "host": local_ip,
            "port": voice_server_port
        }
        
        log(f"🎯 Configuring bridge to push to {local_ip}:{voice_server_port}")
        
        resp = requests.post(
            f"{bridge_url}/configure",
            json=config,
            timeout=10
        )
        
        if resp.ok:
            log("✅ Bridge configured successfully")
            return True
        else:
            log(f"❌ Bridge configuration failed: {resp.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Failed to configure bridge: {e}")
        return False

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Voice Loop - Cooper's Push Architecture")
    parser.add_argument('--port', type=int, default=VOICE_SERVER_PORT,
                       help=f'Voice server port (default: {VOICE_SERVER_PORT})')
    parser.add_argument('--reachy-bridge', default=REACHY_BRIDGE,
                       help=f'Reachy bridge URL (default: {REACHY_BRIDGE})')
    args = parser.parse_args()
    
    # Check requirements
    if not OPENAI_API_KEY:
        log("❌ Set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    global REACHY_BRIDGE
    REACHY_BRIDGE = args.reachy_bridge
    
    log("🤖 Voice Loop starting...")
    log(f"   Bridge: {REACHY_BRIDGE}")
    log(f"   OpenClaw: {OPENCLAW_API}")
    log(f"   TTS Voice: {OPENAI_TTS_VOICE}")
    log(f"   Server Port: {args.port}")
    
    # Test bridge connection
    try:
        resp = requests.get(f"{REACHY_BRIDGE}/status", timeout=5)
        if resp.ok:
            log("✅ Bridge reachable")
        else:
            log("⚠️  Bridge responded with error")
    except Exception as e:
        log(f"❌ Cannot reach bridge: {e}")
        log("   Make sure reachy_bridge.py is running on Reachy")
        sys.exit(1)
    
    # Configure bridge to push to this server
    if not configure_bridge(REACHY_BRIDGE, args.port):
        log("❌ Failed to configure bridge")
        sys.exit(1)
    
    # Start HTTP server
    try:
        server = HTTPServer(('0.0.0.0', args.port), VoiceServerHandler)
        
        # Send startup greeting to Reachy
        log("📢 Sending startup greeting...")
        greeting_audio = generate_speech("Hey! I'm ready to listen.")
        if greeting_audio:
            send_to_reachy(greeting_audio)
        trigger_emotion("cheerful1")
        
        log("")
        log("🎤 Voice Loop ready! Waiting for speech from Reachy...")
        log("   (Ctrl+C to stop)")
        log("")
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        log("")
        log("👋 Stopping voice loop...")
        
        # Send goodbye
        goodbye_audio = generate_speech("Goodbye!")
        if goodbye_audio:
            send_to_reachy(goodbye_audio)
        trigger_emotion("goodbye1")
        time.sleep(2)
        
        log("🛑 Voice loop stopped")

if __name__ == "__main__":
    main()