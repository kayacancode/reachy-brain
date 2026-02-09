#!/usr/bin/env python3
"""
Reachy Mini Voice Loop — Cooper's Push-Based Architecture
========================================================

HTTP server that receives audio from Reachy bridge when speech is detected.
Processes via OpenAI Whisper → KayaCan → OpenAI TTS → sends back to Reachy.

Cooper's Push Architecture (macOS side):
1. HTTP server listens on port 8888
2. POST /audio receives wav chunks from Reachy bridge  
3. Accumulate chunks, detect end-of-speech patterns
4. Process: Whisper transcription → KayaCan response → TTS → POST to Reachy /play
5. No polling — Reachy pushes speech immediately when detected

This is the macOS companion to ~/clawd/skills/reachy-mini/bridge/reachy_bridge.py

Usage: 
  python3 ~/clawd/skills/reachy-mini/voice_loop.py [--port 8888] [--reachy-host 192.168.1.171]

Environment:
  OPENAI_API_KEY — required for Whisper STT and TTS
"""

import os
import sys
import time
import json
import signal
import threading
import requests
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import wave
import io

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / '.env')
except ImportError:
    # Try to source .env manually if dotenv not available
    env_file = Path.home() / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

# Configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENCLAW_ENDPOINT = "http://localhost:18789/v1/chat/completions"
OPENCLAW_TOKEN = "REDACTED_CLAWDBOT_TOKEN"

# Default settings
DEFAULT_PORT = 8888  # Cooper's voice server port
DEFAULT_REACHY_HOST = "10.0.0.68"
REACHY_BRIDGE_PORT = 9000

# Global state
server_running = True
reachy_host = DEFAULT_REACHY_HOST

# Speech accumulation for end-of-speech detection
accumulated_chunks = []
last_audio_time = 0
SPEECH_TIMEOUT = 2.0  # Seconds of silence before processing speech

def log(message):
    """Log with timestamp."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global server_running
    log("🛑 Shutdown requested")
    server_running = False

def transcribe_audio(wav_bytes):
    """Send audio to OpenAI Whisper for transcription."""
    if not wav_bytes or not OPENAI_API_KEY:
        return None
    
    try:
        files = {
            'file': ('audio.wav', wav_bytes, 'audio/wav'),
            'model': (None, 'whisper-1'),
            'language': (None, 'en'),
            'response_format': (None, 'text')
        }
        
        headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
        
        response = requests.post(
            'https://api.openai.com/v1/audio/transcriptions',
            files=files,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            text = response.text.strip()
            if text and text.lower() not in ['', 'you', 'thank you.', 'thanks.']:  # Filter false positives
                return text
        else:
            log(f"❌ Transcription failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        log(f"❌ Transcription error: {e}")
    
    return None

def get_kayacan_response(text):
    """Get response from KayaCan via OpenClaw chat completions."""
    if not text:
        return None
    
    try:
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {
                    "role": "system",
                    "content": "You are KayaCan speaking through a Reachy Mini robot. Keep responses SHORT — 1-2 sentences max. Be natural, conversational, warm. You're physically present in the room talking to someone. Don't use emojis or markdown — this will be spoken aloud."
                },
                {
                    "role": "user", 
                    "content": text
                }
            ],
            "max_tokens": 100,
            "temperature": 0.7
        }
        
        headers = {
            'Authorization': f'Bearer {OPENCLAW_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        log(f"🔄 Calling OpenClaw: {OPENCLAW_ENDPOINT}")
        response = requests.post(OPENCLAW_ENDPOINT, json=payload, headers=headers, timeout=15)
        log(f"🔄 OpenClaw status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            log(f"🔄 OpenClaw raw: {data}")
            if 'choices' in data and data['choices']:
                return data['choices'][0]['message']['content'].strip()
        else:
            log(f"❌ KayaCan response failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        log(f"❌ KayaCan response error: {e}")
    
    return None

def text_to_speech(text):
    """Convert text to speech using OpenAI TTS."""
    if not text or not OPENAI_API_KEY:
        return None
    
    try:
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": "nova",  # Cooper specified nova voice
            "response_format": "wav"
        }
        
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://api.openai.com/v1/audio/speech',
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            return response.content
        else:
            log(f"❌ TTS failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        log(f"❌ TTS error: {e}")
    
    return None

def play_audio_on_reachy(wav_bytes):
    """Send audio to Reachy bridge for playback."""
    if not wav_bytes:
        return False
    
    try:
        url = f"http://{reachy_host}:{REACHY_BRIDGE_PORT}/play"
        response = requests.post(
            url,
            data=wav_bytes,
            headers={'Content-Type': 'audio/wav'},
            timeout=10
        )
        
        if response.status_code == 200:
            return True
        else:
            log(f"❌ Reachy playback failed: {response.status_code}")
            
    except Exception as e:
        log(f"❌ Reachy playback error: {e}")
    
    return False

def concatenate_audio_chunks(chunks):
    """Concatenate multiple wav chunks into single wav file."""
    if not chunks:
        return None
    
    # Extract audio data from each WAV chunk (skip headers)
    all_frames = b''
    sample_rate = 16000  # Known from bridge
    channels = 1
    
    for wav_bytes in chunks:
        try:
            with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
                frames = wav.readframes(wav.getnframes())
                all_frames += frames
        except Exception as e:
            log(f"⚠️  Skipping malformed chunk: {e}")
            continue
    
    if not all_frames:
        return None
    
    # Create combined WAV
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as out_wav:
        out_wav.setnchannels(channels)
        out_wav.setsampwidth(2)  # 16-bit
        out_wav.setframerate(sample_rate)
        out_wav.writeframes(all_frames)
    buf.seek(0)
    return buf.read()

def process_speech_sequence(chunks):
    """Process accumulated speech chunks through the full pipeline."""
    log(f"🎤 Processing speech sequence ({len(chunks)} chunks)")
    
    # Concatenate chunks
    wav_data = concatenate_audio_chunks(chunks)
    if not wav_data:
        log("❌ Failed to concatenate audio chunks")
        return
    
    # Transcribe
    transcript = transcribe_audio(wav_data)
    if not transcript:
        log("❌ No transcription")
        return
    
    log(f"📝 Heard: \"{transcript}\"")
    
    # Get response
    response = get_kayacan_response(transcript)
    if not response:
        log("❌ No response from KayaCan")
        return
    
    log(f"💬 KayaCan: \"{response}\"")
    
    # Convert to speech
    tts_audio = text_to_speech(response)
    if not tts_audio:
        log("❌ TTS failed")
        return
    
    # Play through Reachy
    if play_audio_on_reachy(tts_audio):
        log("✅ Response played on Reachy")
    else:
        log("❌ Reachy playback failed")

def check_speech_timeout():
    """Background thread to process speech when timeout reached."""
    global accumulated_chunks, last_audio_time
    
    while server_running:
        time.sleep(0.5)  # Check twice per second
        
        if accumulated_chunks and (time.time() - last_audio_time) > SPEECH_TIMEOUT:
            # Speech sequence complete - process it
            chunks_to_process = accumulated_chunks.copy()
            accumulated_chunks.clear()
            
            # Process in separate thread to avoid blocking
            threading.Thread(
                target=process_speech_sequence,
                args=(chunks_to_process,),
                daemon=True
            ).start()

def register_with_bridge(server_port):
    """Register our endpoint with the Reachy bridge."""
    try:
        # Get our IP address that the bridge can reach
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to remote IP to get local IP
        local_ip = s.getsockname()[0]
        s.close()
        
        log(f"🎯 Registering with Reachy bridge at {reachy_host}:{REACHY_BRIDGE_PORT}")
        log(f"🎯 Our endpoint: http://{local_ip}:{server_port}")
        
        payload = {"host": local_ip, "port": server_port}
        response = requests.post(
            f"http://{reachy_host}:{REACHY_BRIDGE_PORT}/configure",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            log("✅ Registered with Reachy bridge - continuous listening started")
        else:
            log(f"❌ Bridge registration failed: {response.status_code}")
            
    except Exception as e:
        log(f"❌ Failed to register with bridge: {e}")

class VoiceLoopHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Use our custom logging
        pass

    def do_GET(self):
        if self.path == '/' or self.path == '/status':
            # Status endpoint
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            status = {
                "server": "voice_loop",
                "architecture": "Cooper's Push-Based",
                "status": "running",
                "openai_key": "configured" if OPENAI_API_KEY else "missing",
                "reachy_host": reachy_host,
                "reachy_bridge_port": REACHY_BRIDGE_PORT,
                "openclaw": OPENCLAW_ENDPOINT,
                "accumulated_chunks": len(accumulated_chunks),
                "speech_timeout": SPEECH_TIMEOUT
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global accumulated_chunks, last_audio_time
        
        if self.path == '/audio':
            # Receive audio chunk from Reachy bridge
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                wav_bytes = self.rfile.read(content_length)
                
                log(f"🚀 Received audio chunk from Reachy ({len(wav_bytes)} bytes)")
                
                # Add to accumulated chunks
                accumulated_chunks.append(wav_bytes)
                last_audio_time = time.time()
                
                # Quick response to bridge
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    "status": "received", 
                    "bytes": len(wav_bytes),
                    "total_chunks": len(accumulated_chunks)
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                log(f"❌ Audio processing error: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def main():
    """Main entry point."""
    global server_running, reachy_host
    
    # Parse command line args
    parser = argparse.ArgumentParser(description="Reachy Voice Loop - Cooper's Push Architecture")
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                       help=f'HTTP server port (default: {DEFAULT_PORT})')
    parser.add_argument('--reachy-host', default=DEFAULT_REACHY_HOST,
                       help=f'Reachy bridge host IP (default: {DEFAULT_REACHY_HOST})')
    args = parser.parse_args()
    
    reachy_host = args.reachy_host
    
    # Check requirements
    if not OPENAI_API_KEY:
        log("❌ OPENAI_API_KEY not found in environment")
        return 1
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log("🚀 Starting Reachy Voice Loop (Cooper's Push Architecture)")
    log(f"🎯 Listening for audio chunks on port {args.port}")
    log(f"🤖 Reachy bridge: {reachy_host}:{REACHY_BRIDGE_PORT}")
    log(f"⏱️  Speech timeout: {SPEECH_TIMEOUT}s")
    
    try:
        # Start speech timeout monitor
        timeout_thread = threading.Thread(target=check_speech_timeout, daemon=True)
        timeout_thread.start()
        
        # Create HTTP server
        httpd = HTTPServer(('0.0.0.0', args.port), VoiceLoopHandler)
        
        # Register with bridge in background
        threading.Thread(
            target=register_with_bridge,
            args=(args.port,),
            daemon=True
        ).start()
        
        log("✅ Voice loop server ready - waiting for audio from Reachy")
        
        # Run server with periodic status checks
        httpd.timeout = 1.0  # Check server_running flag every second
        while server_running:
            httpd.handle_request()
            
    except Exception as e:
        log(f"💥 Server error: {e}")
        return 1
    finally:
        log("👋 Voice loop server stopped")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())