#!/usr/bin/env python3
"""
Test Voice Loop Components — validates each piece of the Reachy voice system

Tests:
1. Reachy bridge connectivity and status
2. OpenAI API access (Whisper + TTS)
3. OpenClaw chat completions API
4. End-to-end voice loop (if bridge is working)

Usage:
    source ~/.env && python3 test_voice_loop.py
"""

import os
import sys
import requests
import tempfile
import json

REACHY_BRIDGE = "http://192.168.1.171:9000"
OPENCLAW_API = "http://localhost:18789"
OPENCLAW_TOKEN = "REDACTED_CLAWDBOT_TOKEN"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

def test_bridge():
    """Test Reachy bridge connectivity."""
    print("🌉 Testing Reachy bridge...")
    try:
        resp = requests.get(f"{REACHY_BRIDGE}/status", timeout=5)
        if resp.ok:
            status = resp.json()
            print(f"✅ Bridge connected: {status.get('bridge', 'unknown')}")
            print(f"   SDK: {status.get('sdk', 'unknown')}")
            print(f"   Daemon: {status.get('daemon', {}).get('error', 'OK')}")
            return True
        else:
            print(f"❌ Bridge returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Bridge connection failed: {e}")
        return False

def test_openai():
    """Test OpenAI API access."""
    print("🤖 Testing OpenAI APIs...")
    
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    # Test TTS
    try:
        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "tts-1",
                "input": "Testing voice synthesis",
                "voice": "shimmer",
                "response_format": "wav",
            },
            timeout=10,
        )
        if resp.ok:
            print(f"✅ TTS API working ({len(resp.content)} bytes)")
        else:
            print(f"❌ TTS API failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ TTS API error: {e}")
        return False
    
    # Test Whisper with a dummy file
    try:
        # Create a minimal valid WAV file
        import wave, struct
        temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        with wave.open(temp_wav.name, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) 
            wf.setframerate(16000)
            # Write 0.1 seconds of silence
            wf.writeframes(struct.pack('<h', 0) * 1600)
        
        with open(temp_wav.name, 'rb') as f:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": ("test.wav", f, "audio/wav")},
                data={"model": "whisper-1"},
                timeout=10,
            )
        os.unlink(temp_wav.name)
        
        if resp.ok:
            print(f"✅ Whisper API working")
        else:
            print(f"❌ Whisper API failed: {resp.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Whisper API error: {e}")
        return False
    
    return True

def test_openclaw():
    """Test OpenClaw chat completions."""
    print("🗣️  Testing OpenClaw chat API...")
    try:
        resp = requests.post(
            f"{OPENCLAW_API}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENCLAW_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Say hello in 5 words"}],
                "max_tokens": 50,
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            response_text = data["choices"][0]["message"]["content"]
            print(f"✅ OpenClaw API working: \"{response_text}\"")
            return True
        else:
            print(f"❌ OpenClaw API failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"❌ OpenClaw API error: {e}")
        return False

def test_bridge_audio():
    """Test bridge audio recording if available."""
    print("🎤 Testing bridge audio recording...")
    try:
        resp = requests.get(f"{REACHY_BRIDGE}/listen?duration=2", timeout=10)
        if resp.ok and len(resp.content) > 100:
            peak = float(resp.headers.get("X-Raw-Peak", "0"))
            print(f"✅ Bridge recording working (peak: {peak:.4f})")
            return True
        else:
            print(f"❌ Bridge recording failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Bridge recording error: {e}")
        return False

def main():
    print("🧪 Reachy Voice Loop System Test\n")
    
    results = []
    
    # Test each component
    results.append(("Bridge", test_bridge()))
    results.append(("OpenAI", test_openai()))
    results.append(("OpenClaw", test_openclaw()))
    
    # Only test bridge audio if bridge is working
    if results[0][1]:
        results.append(("Bridge Audio", test_bridge_audio()))
    
    print("\n📊 Test Results:")
    print("=" * 30)
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<12} {status}")
        if not passed:
            all_passed = False
    
    print("\n🎯 Overall Status:")
    if all_passed:
        print("✅ All systems operational! Voice loop ready to run.")
        print("\nTo start voice loop:")
        print("    source ~/.env && python3 voice_loop.py")
    else:
        print("❌ Some components failed. Check configuration and robot status.")
        if not results[0][1]:  # Bridge failed
            print("\n🔧 Bridge issues suggest robot daemon problems.")
            print("Try: curl -X POST 'http://192.168.1.171:8000/api/daemon/start?wake_up=true'")

if __name__ == "__main__":
    main()