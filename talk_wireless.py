#!/usr/bin/env python3
"""Direct conversation with Reachy - wireless version using arecord/aplay.

Run this ON the robot:
  ssh pollen@192.168.23.66
  python3 talk_wireless.py
"""

import asyncio
import io
import logging
import os
import subprocess
import tempfile
import wave

import httpx
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CLAWDBOT_ENDPOINT = os.getenv("CLAWDBOT_ENDPOINT", "")
CLAWDBOT_TOKEN = os.getenv("CLAWDBOT_TOKEN", "")
CLAWDBOT_MODEL = os.getenv("CLAWDBOT_MODEL", "claude-sonnet-4-20250514")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "REDACTED_VOICE_ID")

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 2  # Reachy mic is stereo
AUDIO_DEVICE = "default"
CHUNK_SECONDS = 1  # Record in 1 second chunks (arecord needs integer)

# VAD settings
SILENCE_THRESHOLD = 0.01  # RMS threshold (0-1 range for float audio)
SILENCE_CHUNKS = 2  # Number of silent chunks to end utterance
MIN_SPEECH_CHUNKS = 1  # Minimum chunks of speech to process


class WirelessConversation:
    """Conversation loop using arecord/aplay for wireless operation."""

    def __init__(self):
        self.http_client: httpx.AsyncClient | None = None
        self.history = [
            {"role": "system", "content": "You are Reachy, a friendly robot. Keep responses brief - 1-2 sentences."}
        ]
        self._is_speaking = False

    async def start(self):
        """Initialize HTTP client."""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("🎤 Ready! Start talking...")

    async def stop(self):
        """Clean up."""
        if self.http_client:
            await self.http_client.aclose()

    def _record_chunk(self) -> tuple[bytes, float]:
        """Record a short audio chunk, return (audio_bytes, rms_energy)."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name

        try:
            subprocess.run([
                'arecord', '-D', AUDIO_DEVICE,
                '-f', 'S16_LE', '-r', str(SAMPLE_RATE), '-c', str(CHANNELS),
                '-d', str(CHUNK_SECONDS), '-q', temp_path
            ], capture_output=True, timeout=5)

            with open(temp_path, 'rb') as f:
                audio_bytes = f.read()

            # Calculate RMS energy
            # Skip WAV header (44 bytes)
            if len(audio_bytes) > 44:
                samples = np.frombuffer(audio_bytes[44:], dtype=np.int16)
                # If stereo, take left channel only for RMS
                if CHANNELS == 2:
                    samples = samples[::2]
                rms = np.sqrt(np.mean((samples.astype(np.float32) / 32767) ** 2))
            else:
                rms = 0.0

            return audio_bytes, rms

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    async def listen(self) -> bytes | None:
        """Listen for speech, return complete utterance when user stops talking."""
        chunks = []
        silence_count = 0
        speech_count = 0

        logger.info("🎤 Listening...")

        while True:
            # Don't listen while speaking (prevent feedback)
            if self._is_speaking:
                await asyncio.sleep(0.1)
                continue

            # Record a chunk
            audio_bytes, rms = await asyncio.to_thread(self._record_chunk)

            # Show RMS level for debugging
            bar = "█" * int(rms * 100)
            print(f"\r  RMS: {rms:.3f} [{bar:<20}]", end="", flush=True)

            if rms > SILENCE_THRESHOLD:
                # Speech detected
                chunks.append(audio_bytes)
                speech_count += 1
                silence_count = 0
                print(f" 🎙️ speech ({speech_count})", flush=True)
            else:
                # Silence
                if chunks:  # Only count silence after speech started
                    silence_count += 1
                    print(f" ... silence ({silence_count}/{SILENCE_CHUNKS})", flush=True)

                    if silence_count >= SILENCE_CHUNKS:
                        # End of utterance
                        if speech_count >= MIN_SPEECH_CHUNKS:
                            logger.info("📝 Processing...")
                            return self._combine_wav_chunks(chunks)
                        else:
                            # Too short, reset
                            chunks = []
                            speech_count = 0
                            silence_count = 0
                            logger.info("🎤 Listening...")

    def _combine_wav_chunks(self, chunks: list[bytes]) -> bytes:
        """Combine multiple WAV files into one."""
        if not chunks:
            return b''

        # Extract raw audio from each chunk (skip headers)
        raw_audio = b''
        for chunk in chunks:
            if len(chunk) > 44:
                raw_audio += chunk[44:]

        # Create new WAV with combined audio
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(raw_audio)

        return wav_buffer.getvalue()

    async def transcribe(self, audio_bytes: bytes) -> str | None:
        """Transcribe audio using Whisper."""
        if not audio_bytes or len(audio_bytes) < 1000:
            return None

        try:
            response = await self.http_client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"model": "whisper-1"}
            )

            if response.status_code == 200:
                text = response.json().get("text", "").strip()
                # Filter Whisper hallucinations
                if text and len(text) > 1 and text.lower() not in [
                    "thank you.", "thanks for watching.", "you", "bye.",
                    "the end.", "thanks for watching!", "thank you for watching."
                ]:
                    return text
            else:
                logger.error(f"Whisper error: {response.status_code}")

        except Exception as e:
            logger.error(f"Transcription error: {e}")

        return None

    async def think(self, text: str) -> str | None:
        """Get response from Clawdbot."""
        self.history.append({"role": "user", "content": text})

        try:
            response = await self.http_client.post(
                CLAWDBOT_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {CLAWDBOT_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={"model": CLAWDBOT_MODEL, "messages": self.history}
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                self.history.append({"role": "assistant", "content": content})

                # Keep history manageable
                if len(self.history) > 20:
                    self.history = self.history[:1] + self.history[-18:]

                return content
            else:
                logger.error(f"Clawdbot error: {response.status_code}")

        except Exception as e:
            logger.error(f"Chat error: {e}")

        return None

    async def speak(self, text: str) -> None:
        """Convert text to speech and play."""
        if not text:
            return

        self._is_speaking = True

        try:
            response = await self.http_client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
            )

            if response.status_code != 200:
                logger.error(f"TTS error: {response.status_code}")
                return

            # Save MP3 to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(response.content)
                mp3_path = f.name

            wav_path = mp3_path.replace('.mp3', '.wav')

            try:
                # Convert MP3 to WAV using ffmpeg
                logger.info(f"🔄 Converting {len(response.content)} bytes MP3 to WAV...")
                result = await asyncio.to_thread(
                    subprocess.run,
                    ['ffmpeg', '-y', '-i', mp3_path, '-ar', str(SAMPLE_RATE), '-ac', str(CHANNELS), wav_path],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode != 0:
                    logger.error(f"ffmpeg error: {result.stderr.decode()}")
                    return

                # Play the WAV
                logger.info(f"🔊 Playing audio...")
                result = await asyncio.to_thread(
                    subprocess.run,
                    ['aplay', '-D', AUDIO_DEVICE, wav_path],
                    capture_output=True,
                    timeout=30
                )
                if result.returncode != 0:
                    logger.error(f"aplay error: {result.stderr.decode()}")
            finally:
                if os.path.exists(mp3_path):
                    os.unlink(mp3_path)
                if os.path.exists(wav_path):
                    os.unlink(wav_path)

        except Exception as e:
            logger.error(f"TTS error: {e}")
        finally:
            self._is_speaking = False

    async def run(self):
        """Main conversation loop."""
        await self.start()

        # Greeting
        await self.speak("Hey! I'm ready to chat.")

        try:
            while True:
                # Listen
                audio = await self.listen()
                if not audio:
                    continue

                # Transcribe
                text = await self.transcribe(audio)
                if not text:
                    logger.info("(no speech detected)")
                    continue

                logger.info(f"You: {text}")

                # Think
                response = await self.think(text)
                if not response:
                    continue

                logger.info(f"Reachy: {response}")

                # Speak
                await self.speak(response)

        except KeyboardInterrupt:
            logger.info("\n👋 Goodbye!")
            await self.speak("Bye!")
        finally:
            await self.stop()


async def main():
    print("=" * 50)
    print("🤖 Reachy Direct Talk (Wireless)")
    print("=" * 50)

    # Check env vars
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not CLAWDBOT_ENDPOINT:
        missing.append("CLAWDBOT_ENDPOINT")
    if not CLAWDBOT_TOKEN:
        missing.append("CLAWDBOT_TOKEN")
    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")

    if missing:
        print(f"❌ Missing: {', '.join(missing)}")
        print("\nExport them or create .env:")
        print('  export OPENAI_API_KEY="sk-..."')
        print('  export CLAWDBOT_ENDPOINT="http://YOUR_MAC_IP:18789/v1/chat/completions"')
        print('  export CLAWDBOT_TOKEN="your-token"')
        print('  export ELEVENLABS_API_KEY="sk_..."')
        return

    conv = WirelessConversation()
    await conv.run()


if __name__ == "__main__":
    asyncio.run(main())
