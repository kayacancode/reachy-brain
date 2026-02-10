#!/usr/bin/env python3
"""Direct conversation with Reachy - no Gradio, just talk."""

import asyncio
import io
import logging
import os
import wave
from typing import Optional

import httpx
import numpy as np
from pydub import AudioSegment

from audio import AudioStream, audio_to_int16

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Config from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CLAWDBOT_ENDPOINT = os.getenv("CLAWDBOT_ENDPOINT", "http://localhost:18789/v1/chat/completions")
CLAWDBOT_TOKEN = os.getenv("CLAWDBOT_TOKEN", "")
CLAWDBOT_MODEL = os.getenv("CLAWDBOT_MODEL", "claude-sonnet-4-20250514")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "REDACTED_VOICE_ID")
ROBOT_IP = os.getenv("ROBOT_IP", "192.168.23.66")

# VAD settings
SILENCE_THRESHOLD = 500  # RMS threshold for silence detection
SILENCE_DURATION = 1.0   # Seconds of silence to end utterance
MIN_SPEECH_DURATION = 0.3  # Minimum speech duration to process


class RobotController:
    """Simple robot controller for AudioStream compatibility."""

    def __init__(self):
        self._robot = None

    async def connect(self, ip: str):
        """Connect to robot via SDK."""
        from reachy_mini import ReachyMini
        logger.info(f"🤖 Connecting to Reachy at {ip}...")
        self._robot = ReachyMini(host=ip)
        logger.info("✅ Connected!")

    async def disconnect(self):
        if self._robot:
            self._robot = None


class ConversationLoop:
    """Main conversation loop - listen, think, speak."""

    def __init__(self):
        self.robot = RobotController()
        self.audio: Optional[AudioStream] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self.history = [
            {"role": "system", "content": "You are Reachy, a friendly robot assistant. Keep responses brief and conversational - 1-2 sentences max."}
        ]
        self.sample_rate = 24000

    async def start(self):
        """Initialize everything."""
        # Connect to robot
        await self.robot.connect(ROBOT_IP)

        # Setup audio
        self.audio = AudioStream(
            robot_controller=self.robot,
            input_sample_rate=self.sample_rate,
            output_sample_rate=self.sample_rate
        )
        await self.audio.start()

        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(timeout=30.0)

        logger.info("🎤 Ready! Start talking...")

    async def stop(self):
        """Clean up."""
        if self.audio:
            await self.audio.stop()
        if self.http_client:
            await self.http_client.aclose()
        await self.robot.disconnect()

    async def listen(self) -> Optional[bytes]:
        """Listen for speech, return audio when user stops talking."""
        chunks = []
        silence_samples = 0
        speech_samples = 0
        samples_per_second = self.sample_rate

        async for chunk in self.audio.audio_generator():
            if not chunk:
                continue

            # Calculate RMS energy
            audio_array = np.frombuffer(chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))

            if rms > SILENCE_THRESHOLD:
                # Speech detected
                chunks.append(chunk)
                speech_samples += len(audio_array)
                silence_samples = 0
            else:
                # Silence
                if chunks:  # Only count silence after speech started
                    chunks.append(chunk)
                    silence_samples += len(audio_array)

                    # Check if enough silence to end utterance
                    if silence_samples >= SILENCE_DURATION * samples_per_second:
                        # Check minimum speech duration
                        if speech_samples >= MIN_SPEECH_DURATION * samples_per_second:
                            logger.info("📝 Processing...")
                            return b''.join(chunks)
                        else:
                            # Too short, reset
                            chunks = []
                            speech_samples = 0
                            silence_samples = 0

        return None

    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe audio using Whisper."""
        if not audio_bytes or len(audio_bytes) < 1000:
            return None

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(audio_bytes)
        wav_buffer.seek(0)

        try:
            response = await self.http_client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": ("audio.wav", wav_buffer, "audio/wav")},
                data={"model": "whisper-1"}
            )

            if response.status_code == 200:
                text = response.json().get("text", "").strip()
                # Filter out common Whisper hallucinations
                if text and len(text) > 1 and text.lower() not in [
                    "thank you.", "thanks for watching.", "you", "bye.",
                    "the end.", "thanks for watching!"
                ]:
                    return text
            else:
                logger.error(f"Whisper error: {response.text}")
        except Exception as e:
            logger.error(f"Transcription error: {e}")

        return None

    async def think(self, text: str) -> Optional[str]:
        """Get response from Clawdbot."""
        self.history.append({"role": "user", "content": text})

        try:
            response = await self.http_client.post(
                CLAWDBOT_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {CLAWDBOT_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": CLAWDBOT_MODEL,
                    "messages": self.history
                }
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                self.history.append({"role": "assistant", "content": content})

                # Keep history manageable
                if len(self.history) > 20:
                    self.history = self.history[:1] + self.history[-18:]

                return content
            else:
                logger.error(f"Clawdbot error: {response.text}")
        except Exception as e:
            logger.error(f"Chat error: {e}")

        return None

    async def speak(self, text: str) -> None:
        """Convert text to speech and play."""
        if not text:
            return

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
                logger.error(f"TTS error: {response.text}")
                return

            # Convert MP3 to PCM at correct sample rate
            audio_segment = AudioSegment.from_mp3(io.BytesIO(response.content))
            audio_segment = audio_segment.set_frame_rate(self.sample_rate).set_channels(1)

            # Get raw samples as int16
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

            # Play through robot speaker
            await self.audio.play_audio(samples.tobytes())

        except Exception as e:
            logger.error(f"TTS error: {e}")

    async def run(self):
        """Main conversation loop."""
        await self.start()

        # Greeting
        await self.speak("Hey! I'm ready to chat.")

        try:
            while True:
                # Listen for speech
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
    print("🤖 Reachy Direct Talk")
    print("=" * 50)

    # Check required env vars
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not CLAWDBOT_TOKEN:
        missing.append("CLAWDBOT_TOKEN")
    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")

    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("Set them in .env or export them")
        return

    loop = ConversationLoop()
    await loop.run()


if __name__ == "__main__":
    asyncio.run(main())
