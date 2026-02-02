#!/usr/bin/env python3
"""
Voice loop for Reachy Mini + KayaCan brain.
Uses macOS `say` for TTS (Chatterbox upgrade later).

Usage:
    python voice_loop.py --local-mic --local-speaker  # Test locally
    python voice_loop.py                               # Use Reachy mic/speaker
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Config
REACHY_HOST = os.environ.get("REACHY_HOST", "192.168.1.171")
REACHY_PORT = os.environ.get("REACHY_PORT", "8042")
REACHY_BASE = f"http://{REACHY_HOST}:{REACHY_PORT}"
REACHY_SSH_USER = os.environ.get("REACHY_SSH_USER", "pollen")
REACHY_SSH_PASS = os.environ.get("REACHY_SSH_PASS", "root")

CLAWDBOT_HOST = os.environ.get("CLAWDBOT_HOST", "localhost")
CLAWDBOT_PORT = os.environ.get("CLAWDBOT_PORT", "18789")
CLAWDBOT_TOKEN = os.environ.get("CLAWDBOT_TOKEN", "REDACTED_CLAWDBOT_TOKEN")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
HONCHO_API_KEY = os.environ.get("HONCHO_API_KEY", "")
MACOS_VOICE = os.environ.get("MACOS_VOICE", "Samantha")  # Try: Samantha, Alex, Ava

# Chatterbox via HuggingFace
CHATTERBOX_SPACE = "ResembleAI/chatterbox-turbo-demo"
USE_CHATTERBOX = True  # Set to False to use macOS say


def reachy_api(method: str, path: str, data: dict = None) -> dict:
    """Call Reachy API."""
    try:
        url = f"{REACHY_BASE}{path}"
        if method == "GET":
            with urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())
        else:
            req = Request(url, data=json.dumps(data or {}).encode(),
                         headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
    except URLError as e:
        return {"error": str(e)}


def record_audio_local(duration: float = 5.0) -> str:
    """Record audio from local microphone using sox."""
    output = tempfile.mktemp(suffix=".wav")
    print(f"   [Recording {duration}s...]")
    try:
        # Use sox/rec
        subprocess.run([
            "rec", "-q", output, "rate", "16k", "channels", "1",
            "trim", "0", str(duration)
        ], check=True, timeout=duration + 5, capture_output=True)
        return output
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to ffmpeg
        try:
            subprocess.run([
                "ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
                "-t", str(duration), "-ar", "16000", "-ac", "1", output
            ], check=True, capture_output=True, timeout=duration + 10)
            return output
        except Exception as e:
            print(f"   Recording failed: {e}")
            return None


def record_audio_reachy(duration: float = 15.0) -> str:
    """Record audio from Reachy's microphone with silence detection."""
    print("   [Listening... (speak now, stops on silence)]")
    reachy_api("POST", "/api/audio/start_recording")
    
    # Poll for silence - check every 0.5s if recording is still active
    # Max duration as safety net
    elapsed = 0
    poll_interval = 0.5
    while elapsed < duration:
        time.sleep(poll_interval)
        elapsed += poll_interval
    
    result = reachy_api("POST", "/api/audio/stop_recording")
    
    if "error" in result:
        print(f"   Recording error: {result['error']}")
        return None
    
    if "filename" in result:
        try:
            url = f"{REACHY_BASE}/api/audio/download/{result['filename']}"
            with urlopen(url, timeout=30) as resp:
                audio_data = resp.read()
            output = tempfile.mktemp(suffix=".wav")
            with open(output, "wb") as f:
                f.write(audio_data)
            
            # Trim silence from the audio
            trimmed = trim_silence(output)
            return trimmed if trimmed else output
        except Exception as e:
            print(f"   Download failed: {e}")
    return None


def trim_silence(audio_path: str, aggressiveness: int = 2) -> str:
    """Trim trailing silence from audio using webrtcvad."""
    try:
        import wave
        import webrtcvad
        
        vad = webrtcvad.Vad(aggressiveness)  # 0-3, higher = more aggressive
        
        with wave.open(audio_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            audio = wf.readframes(wf.getnframes())
        
        # webrtcvad needs 16kHz mono 16-bit
        if sample_rate not in (8000, 16000, 32000, 48000):
            return audio_path  # Can't process, return as-is
        
        # Frame duration must be 10, 20, or 30 ms
        frame_duration_ms = 30
        frame_size = int(sample_rate * frame_duration_ms / 1000) * sample_width * num_channels
        
        # Find last frame with speech
        last_speech_end = 0
        silence_frames = 0
        silence_threshold = int(1500 / frame_duration_ms)  # 1.5s of silence = done
        
        offset = 0
        while offset + frame_size <= len(audio):
            frame = audio[offset:offset + frame_size]
            try:
                is_speech = vad.is_speech(frame, sample_rate)
            except:
                is_speech = True  # Assume speech if VAD fails
            
            if is_speech:
                last_speech_end = offset + frame_size
                silence_frames = 0
            else:
                silence_frames += 1
            
            offset += frame_size
        
        if last_speech_end > 0 and last_speech_end < len(audio):
            # Add a small buffer after last speech
            buffer = int(0.3 * sample_rate * sample_width * num_channels)
            trim_point = min(last_speech_end + buffer, len(audio))
            
            trimmed_path = audio_path.replace('.wav', '_trimmed.wav')
            with wave.open(trimmed_path, 'wb') as wf:
                wf.setnchannels(num_channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(audio[:trim_point])
            
            duration_s = trim_point / (sample_rate * sample_width * num_channels)
            print(f"   [Trimmed to {duration_s:.1f}s]")
            return trimmed_path
        
        return audio_path
    except ImportError:
        return audio_path
    except Exception as e:
        print(f"   Trim error: {e}")
        return audio_path


def transcribe_whisper(audio_path: str) -> str:
    """Transcribe audio with Whisper."""
    try:
        result = subprocess.run([
            "whisper", audio_path,
            "--model", WHISPER_MODEL,
            "--output_format", "txt",
            "--output_dir", "/tmp",
            "--language", "en"
        ], capture_output=True, text=True, timeout=60)
        
        # Read the output txt file
        txt_path = Path("/tmp") / (Path(audio_path).stem + ".txt")
        if txt_path.exists():
            text = txt_path.read_text().strip()
            txt_path.unlink()
            return text
    except Exception as e:
        print(f"   Whisper error: {e}")
    return ""


def get_honcho_context(message: str) -> str:
    """Get personalized context from Honcho about Kaya."""
    if not HONCHO_API_KEY:
        return ""
    
    try:
        from honcho import Honcho
        client = Honcho(api_key=HONCHO_API_KEY, workspace_id="forever22")
        kaya = client.peer("kaya")
        response = kaya.chat(f"The user just said: '{message}'. What context about them would help me respond better and more personally?")
        return response if response else ""
    except Exception as e:
        print(f"   Honcho: {e}")
        return ""


def save_to_honcho(user_text: str, assistant_text: str):
    """Save interaction to Honcho for future memory."""
    if not HONCHO_API_KEY:
        return
    
    try:
        from honcho import Honcho
        client = Honcho(api_key=HONCHO_API_KEY, workspace_id="forever22")
        kaya = client.peer("kaya")
        kayacan = client.peer("kayacan")
        
        session_name = f"reachy-{time.strftime('%Y-%m-%d')}"
        session = client.session(session_name)
        
        session.add_messages([
            kaya.message(user_text),
            kayacan.message(assistant_text)
        ])
        print("   💾 Saved to Honcho")
    except Exception as e:
        print(f"   Honcho save: {e}")


def send_to_clawdbot(message: str) -> str:
    """Send message to Clawdbot via OpenAI-compatible API."""
    url = f"http://{CLAWDBOT_HOST}:{CLAWDBOT_PORT}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CLAWDBOT_TOKEN}"
    }
    
    # Get Honcho context
    honcho_context = get_honcho_context(message)
    memory_note = f"\n\nMemory context about Kaya: {honcho_context}" if honcho_context else ""
    
    system_prompt = f"You are KayaCan, speaking through Reachy Mini robot. Keep responses concise and conversational (under 2-3 sentences). You're having a voice conversation.{memory_note}"
    
    payload = {
        "model": "clawdbot:main",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "user": "reachy-voice-loop"
    }
    
    try:
        req = Request(url, 
                     data=json.dumps(payload).encode(),
                     headers=headers, method="POST")
        with urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            # OpenAI format: choices[0].message.content
            response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            # Clean up response for speech
            response = clean_for_speech(response)
            return response if response else "I'm not sure how to respond to that."
    except Exception as e:
        print(f"   Clawdbot error: {e}")
        return "Sorry, I couldn't process that."


def clean_for_speech(text: str) -> str:
    """Clean text for TTS - remove markdown, emojis, etc."""
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # italic
    text = re.sub(r'`(.+?)`', r'\1', text)        # code
    text = re.sub(r'#{1,6}\s*', '', text)         # headers
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # links
    
    # Remove common emojis (keep text readable)
    text = re.sub(r'[🫧🤖✨🔥👋💡🎯📝🎤🧠🗣️☀️]', '', text)
    
    # Clean up whitespace
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()[:500]  # Limit length for TTS


def speak_macos(text: str, output_path: str = None) -> str:
    """Generate speech with macOS say command."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".aiff")
    
    try:
        subprocess.run([
            "say", "-v", MACOS_VOICE, "-o", output_path, text
        ], check=True, timeout=30)
        return output_path
    except Exception as e:
        print(f"   TTS error: {e}")
        return None


def speak_chatterbox(text: str, output_path: str = None) -> str:
    """Generate speech with Chatterbox via HuggingFace Space."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".wav")
    
    try:
        # Import here to avoid startup delay
        from gradio_client import Client
        
        client = Client(CHATTERBOX_SPACE, verbose=False)
        result = client.predict(
            text=text,
            audio_prompt_path=None,
            temperature=0.8,
            seed_num=42,
            min_p=0.0,
            top_p=0.95,
            top_k=1000,
            repetition_penalty=1.2,
            norm_loudness=True,
            api_name='/generate'
        )
        
        # Copy to our output path
        import shutil
        shutil.copy(result, output_path)
        return output_path
    except Exception as e:
        print(f"   Chatterbox error: {e}")
        print("   Falling back to macOS voice...")
        return speak_macos(text, output_path.replace('.wav', '.aiff'))


def speak(text: str, output_path: str = None) -> str:
    """Generate speech with configured TTS."""
    if USE_CHATTERBOX:
        return speak_chatterbox(text, output_path)
    else:
        return speak_macos(text, output_path)


def play_audio_local(audio_path: str):
    """Play audio on local speaker."""
    try:
        subprocess.run(["afplay", audio_path], check=True, timeout=60)
    except Exception as e:
        print(f"   Playback error: {e}")


def play_audio_reachy(audio_path: str):
    """Play audio on Reachy's speaker via SCP + API."""
    try:
        # Convert to wav if needed
        wav_path = audio_path
        if audio_path.endswith('.aiff'):
            wav_path = audio_path.replace('.aiff', '.wav')
            subprocess.run([
                "ffmpeg", "-y", "-i", audio_path, "-ar", "44100", wav_path
            ], check=True, capture_output=True, timeout=30)
        
        # SCP to Reachy recordings directory using sshpass
        filename = f"kayacan_{int(time.time())}.wav"
        remote_path = f"/tmp/reachy_mini_testbench/recordings/{filename}"
        
        subprocess.run([
            "sshpass", "-p", REACHY_SSH_PASS,
            "scp", "-o", "StrictHostKeyChecking=no",
            wav_path, f"{REACHY_SSH_USER}@{REACHY_HOST}:{remote_path}"
        ], check=True, capture_output=True, timeout=30)
        
        # Play via API
        result = reachy_api("POST", f"/api/audio/play/{filename}")
        if result.get("success"):
            print("   [Played on Reachy]")
        else:
            print(f"   Reachy API error: {result}")
            play_audio_local(audio_path)
        
    except Exception as e:
        print(f"   Reachy playback error: {e}")
        print("   Falling back to local speaker...")
        play_audio_local(audio_path)


def move_reachy(emotion: str = "neutral"):
    """Move Reachy based on emotional context."""
    movements = {
        "listening": {"pitch": 5, "yaw": 0, "roll": 3},
        "thinking": {"pitch": 10, "yaw": 10, "roll": 0},
        "speaking": {"pitch": 0, "yaw": 0, "roll": 0},
        "happy": {"pitch": 5, "yaw": 0, "roll": 5},
        "neutral": {"pitch": 0, "yaw": 0, "roll": 0},
    }
    move = movements.get(emotion, movements["neutral"])
    reachy_api("POST", "/api/move_head", {**move, "duration": 0.3})


def main_loop(use_local_mic: bool = False, use_local_speaker: bool = False,
              listen_duration: float = 5.0, push_to_talk: bool = False):
    """Main voice interaction loop."""
    print("\n🤖 Reachy + KayaCan Voice Loop")
    print("=" * 40)
    print(f"  Reachy: {REACHY_BASE}")
    print(f"  Mic: {'local' if use_local_mic else 'reachy'}")
    print(f"  Speaker: {'local' if use_local_speaker else 'reachy'}")
    print(f"  Voice: {MACOS_VOICE}")
    print(f"  Listen duration: {listen_duration}s")
    print("=" * 40)
    print("\nPress Ctrl+C to stop")
    if push_to_talk:
        print("Press ENTER to start listening...\n")
    else:
        print("Continuous listening mode...\n")
    
    try:
        while True:
            # Wait for push-to-talk if enabled
            if push_to_talk:
                input("🎤 Press ENTER to speak > ")
            
            # 1. Visual cue
            move_reachy("listening")
            print("🎤 Listening...")
            
            # 2. Record audio
            if use_local_mic:
                audio_path = record_audio_local(listen_duration)
            else:
                audio_path = record_audio_reachy(listen_duration)
            
            if not audio_path:
                print("   ❌ Recording failed\n")
                continue
            
            # 3. Transcribe
            print("📝 Transcribing...")
            text = transcribe_whisper(audio_path)
            
            # Cleanup recording
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            
            if not text or len(text.strip()) < 2:
                print("   (silence or unclear)\n")
                continue
            
            print(f"👤 You: {text}")
            
            # 4. Send to KayaCan
            print("🧠 Thinking...")
            move_reachy("thinking")
            response = send_to_clawdbot(text)
            print(f"🤖 KayaCan: {response}")
            
            # 5. Generate TTS
            print("🗣️ Speaking..." + (" (Chatterbox)" if USE_CHATTERBOX else " (macOS)"))
            move_reachy("speaking")
            tts_path = speak(response)
            
            if tts_path:
                # 6. Play response
                if use_local_speaker:
                    play_audio_local(tts_path)
                else:
                    play_audio_reachy(tts_path)
                
                # Cleanup
                if os.path.exists(tts_path):
                    os.unlink(tts_path)
            
            # 7. Save to Honcho for memory
            save_to_honcho(text, response)
            
            move_reachy("neutral")
            print()  # Blank line between interactions
            
            if not push_to_talk:
                time.sleep(0.5)  # Brief pause before next listen
            
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        move_reachy("neutral")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reachy + KayaCan Voice Loop")
    parser.add_argument("--local-mic", action="store_true", help="Use local microphone")
    parser.add_argument("--local-speaker", action="store_true", help="Use local speaker")
    parser.add_argument("--duration", type=float, default=5.0, help="Listen duration (seconds)")
    parser.add_argument("--push-to-talk", action="store_true", help="Wait for ENTER before listening")
    parser.add_argument("--voice", default="Samantha", help="macOS voice (Samantha, Alex, Ava)")
    
    args = parser.parse_args()
    
    if args.voice:
        MACOS_VOICE = args.voice
    
    main_loop(
        use_local_mic=args.local_mic,
        use_local_speaker=args.local_speaker,
        listen_duration=args.duration,
        push_to_talk=args.push_to_talk
    )
