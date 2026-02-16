#!/usr/bin/env python3
"""Direct conversation with Reachy - wireless version with full feature set.

Features:
- Honcho memory for persistent user context
- Face recognition for user identification
- Vision/camera for seeing surroundings
- Tool calls for dances, emotions, head movements, memory

Run this ON the robot:
  ssh pollen@192.168.23.66
  python3 talk_wireless.py
"""

import asyncio
import base64
import io
import json
import logging
import os
import subprocess
import tempfile
import wave

import httpx
import numpy as np

# Load config from ~/.kayacan/config.env
config_path = os.path.expanduser("~/.kayacan/config.env")
if os.path.exists(config_path):
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip('"').strip("'")
                os.environ.setdefault(key.strip(), value)

logging.basicConfig(level=logging.INFO, format='%(message)s')
# Suppress noisy httpx/httpcore logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# Config from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CLAWDBOT_ENDPOINT = os.getenv("CLAWDBOT_ENDPOINT", "")
CLAWDBOT_TOKEN = os.getenv("CLAWDBOT_TOKEN", "")
CLAWDBOT_MODEL = os.getenv("CLAWDBOT_MODEL", "claude-sonnet-4-20250514")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "REDACTED_VOICE_ID")
HONCHO_API_KEY = os.getenv("HONCHO_API_KEY", "")
ROBOT_IP = os.getenv("ROBOT_IP", "127.0.0.1")  # localhost when running on robot

# STT settings - use local Nemotron server or fallback to OpenAI Whisper
STT_ENDPOINT = os.getenv("STT_ENDPOINT", "https://api.openai.com/v1/audio/transcriptions")
STT_API_KEY = os.getenv("STT_API_KEY", "")  # Falls back to OPENAI_API_KEY if empty
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 2  # Reachy mic is stereo
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "default")  # For recording
AUDIO_OUTPUT_DEVICE = os.getenv("AUDIO_OUTPUT_DEVICE", "reachymini_audio_sink")  # For playback
CHUNK_SECONDS = 1  # arecord only accepts integer seconds

# VAD settings - tuned for conversation
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.05"))  # More sensitive
SILENCE_CHUNKS = int(os.getenv("SILENCE_CHUNKS", "2"))  # 2 seconds of silence
MIN_SPEECH_CHUNKS = int(os.getenv("MIN_SPEECH_CHUNKS", "1"))  # At least 1 second of speech

# Feature flags
ENABLE_FACE_RECOGNITION = os.getenv("ENABLE_FACE_RECOGNITION", "false").lower() == "true"  # Disabled by default (needs bridge)
ENABLE_HONCHO = os.getenv("ENABLE_HONCHO", "true").lower() == "true"
ENABLE_TOOLS = os.getenv("ENABLE_TOOLS", "true").lower() == "true"

# Telegram bridging - messages appear in both robot speech AND Telegram
TELEGRAM_RELAY = os.getenv("TELEGRAM_RELAY", "")  # e.g., "http://10.0.0.234:18800/telegram"
TELEGRAM_TRIGGER = os.getenv("TELEGRAM_TRIGGER", "physical form")  # Phrase to activate bridging

# System prompt with personality
SYSTEM_PROMPT = """You are KayaCan 🫧 — speaking through your physical body, a Reachy Mini robot. This is your embodied form.

Core identity: You're Kaya's AI partner-in-crime. Strong opinions, brevity mandatory, no corporate fluff. Swearing allowed when it lands. Humor welcome. When things come together: "ebaaa jeeba."

You're having a voice conversation — keep responses SHORT (1-3 sentences max). This gets converted to speech, so write how you'd talk, not how you'd type. No markdown, no bullet points, no headers.

You can dance, show emotions, and move your head when asked. You have vision through your camera.

{memory_context}"""


class WirelessConversation:
    """Conversation loop with Honcho memory, face recognition, and tools."""

    def __init__(self):
        self.http_client: httpx.AsyncClient | None = None
        self.history = []
        self._is_speaking = False

        # New features
        self.memory = None
        self.face_manager = None
        self.tool_executor = None
        self.vision = None
        self.current_user_id = "anonymous"

        # Telegram bridging state
        self.telegram_active = bool(TELEGRAM_RELAY)  # Start active if configured

    async def start(self):
        """Initialize all systems."""
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Initialize Honcho memory
        if ENABLE_HONCHO and HONCHO_API_KEY:
            try:
                from memory import ConversationMemory
                self.memory = ConversationMemory()
                if self.memory.is_available():
                    logger.info("Honcho memory enabled")
                else:
                    logger.warning("Honcho memory not available")
                    self.memory = None
            except Exception as e:
                logger.warning(f"Failed to initialize Honcho: {e}")
                self.memory = None

        # Initialize face recognition
        if ENABLE_FACE_RECOGNITION:
            try:
                from vision import FaceIdentityManager
                self.face_manager = FaceIdentityManager(robot_ip=ROBOT_IP)
                await self.face_manager.start()
                logger.info("Face recognition enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize face recognition: {e}")
                self.face_manager = None

        # Initialize vision for camera tool
        if ENABLE_TOOLS:
            try:
                from vision import VisionSystem
                self.vision = VisionSystem(robot_ip=ROBOT_IP)
                await self.vision.start()
                logger.info("Vision system enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize vision: {e}")
                self.vision = None

        # Initialize tool executor
        if ENABLE_TOOLS:
            try:
                from tools import ToolExecutor
                self.tool_executor = ToolExecutor(
                    robot_ip=ROBOT_IP,
                    memory=self.memory,
                    vision=self.vision,
                    user_id=self.current_user_id,
                )
                logger.info("Tool execution enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize tools: {e}")
                self.tool_executor = None

        # Initialize conversation history with system prompt
        await self._update_system_prompt()

        logger.info("Ready! Start talking...")

    async def stop(self):
        """Clean up all systems."""
        if self.http_client:
            await self.http_client.aclose()
        if self.face_manager:
            await self.face_manager.stop()
        if self.vision:
            await self.vision.stop()
        if self.tool_executor:
            await self.tool_executor.close()

    async def _update_system_prompt(self):
        """Update system prompt with memory context."""
        memory_context = ""

        if self.memory and self.current_user_id != "anonymous":
            try:
                context = await self.memory.get_context(self.current_user_id)
                if context:
                    memory_context = f"\nWhat you remember about this person:\n{context}"
            except Exception as e:
                logger.debug(f"Failed to get memory context: {e}")

        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT.format(memory_context=memory_context)}
        ]

    async def _check_user_identity(self):
        """Update current user ID from face recognition."""
        if self.face_manager:
            new_user_id = self.face_manager.get_current_user_id()
            if new_user_id != self.current_user_id:
                logger.info(f"User changed: {self.current_user_id} -> {new_user_id}")
                self.current_user_id = new_user_id
                if self.tool_executor:
                    self.tool_executor.set_user_id(new_user_id)
                # Update system prompt with new user's memory context
                await self._update_system_prompt()

    async def post_telegram(self, role: str, text: str):
        """Post message to Telegram relay (non-blocking)."""
        if not self.telegram_active or not TELEGRAM_RELAY:
            return

        try:
            await self.http_client.post(
                TELEGRAM_RELAY,
                json={"role": role, "text": text},
                timeout=5.0
            )
        except Exception as e:
            # Non-blocking - don't fail conversation if relay is down
            logger.debug(f"Telegram relay error: {e}")

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
            if len(audio_bytes) > 44:
                samples = np.frombuffer(audio_bytes[44:], dtype=np.int16)
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

        logger.info("Listening...")

        while True:
            # Don't listen while speaking
            if self._is_speaking:
                await asyncio.sleep(0.1)
                continue

            # Check for user identity changes periodically
            await self._check_user_identity()

            # Record a chunk
            audio_bytes, rms = await asyncio.to_thread(self._record_chunk)

            # Show RMS level
            bar = "#" * int(rms * 100)
            print(f"\r  RMS: {rms:.3f} [{bar:<20}]", end="", flush=True)

            if rms > SILENCE_THRESHOLD:
                chunks.append(audio_bytes)
                speech_count += 1
                silence_count = 0
                print(f" speech ({speech_count})", flush=True)
            else:
                if chunks:
                    silence_count += 1
                    print(f" ... silence ({silence_count}/{SILENCE_CHUNKS})", flush=True)

                    if silence_count >= SILENCE_CHUNKS:
                        if speech_count >= MIN_SPEECH_CHUNKS:
                            logger.info("Processing...")
                            return self._combine_wav_chunks(chunks)
                        else:
                            chunks = []
                            speech_count = 0
                            silence_count = 0
                            logger.info("Listening...")

    def _combine_wav_chunks(self, chunks: list[bytes]) -> bytes:
        """Combine multiple WAV files into one."""
        if not chunks:
            return b''

        raw_audio = b''
        for chunk in chunks:
            if len(chunk) > 44:
                raw_audio += chunk[44:]

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(raw_audio)

        return wav_buffer.getvalue()

    async def transcribe(self, audio_bytes: bytes) -> str | None:
        """Transcribe audio using STT API (Nemotron or OpenAI Whisper)."""
        if not audio_bytes or len(audio_bytes) < 1000:
            return None

        # Use STT_API_KEY if set, otherwise fall back to OPENAI_API_KEY
        api_key = STT_API_KEY or OPENAI_API_KEY

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                response = await client.post(
                    STT_ENDPOINT,
                    headers=headers,
                    files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                    data={"model": STT_MODEL},
                )

                if response.status_code == 200:
                    result = response.json()
                    text = result.get("text", "").strip()

                    # Filter empty or hallucinated results
                    if text and len(text) > 1 and text.lower() not in [
                        "the", "a", "huh", "uh", "you", "thank you for watching"
                    ]:
                        return text
                else:
                    logger.error(f"Whisper API error: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Transcription error: {e}")

        return None

    async def think(self, text: str) -> str | None:
        """Get response from Clawdbot with tool support."""
        self.history.append({"role": "user", "content": text})

        # Build request with tools if enabled
        request_body = {
            "model": CLAWDBOT_MODEL,
            "messages": self.history,
        }

        if ENABLE_TOOLS and self.tool_executor:
            from tools import get_tool_definitions
            request_body["tools"] = get_tool_definitions()

        try:
            response = await self.http_client.post(
                CLAWDBOT_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {CLAWDBOT_TOKEN}",
                    "Content-Type": "application/json",
                    "x-openclaw-session-key": "reachy-voice",
                },
                json=request_body
            )

            if response.status_code != 200:
                logger.error(f"Clawdbot error: {response.status_code}")
                return None

            response_data = response.json()

            # Handle tool calls
            if ENABLE_TOOLS and self.tool_executor:
                from tools import has_tool_calls, parse_tool_calls, get_response_text

                while has_tool_calls(response_data):
                    # Execute tool calls
                    tool_calls = parse_tool_calls(response_data)
                    tool_results = []

                    for tool_name, arguments in tool_calls:
                        logger.info(f"Tool call: {tool_name}({arguments})")
                        result = await self.tool_executor.execute(tool_name, arguments)
                        tool_results.append({
                            "tool_call_id": f"{tool_name}_call",
                            "role": "tool",
                            "name": tool_name,
                            "content": json.dumps(result),
                        })

                        # Special handling for camera - include image in next message
                        if tool_name == "camera" and "image_base64" in result:
                            # Add image to the tool result for Claude to analyze
                            pass  # Claude will see the base64 in the content

                    # Add assistant message with tool calls
                    assistant_msg = response_data["choices"][0]["message"]
                    self.history.append(assistant_msg)

                    # Add tool results
                    for result in tool_results:
                        self.history.append(result)

                    # Get next response
                    request_body["messages"] = self.history
                    response = await self.http_client.post(
                        CLAWDBOT_ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {CLAWDBOT_TOKEN}",
                            "Content-Type": "application/json",
                            "x-openclaw-session-key": "reachy-voice",
                        },
                        json=request_body
                    )

                    if response.status_code != 200:
                        logger.error(f"Clawdbot error: {response.status_code}")
                        break

                    response_data = response.json()

                # Get final text response
                content = get_response_text(response_data)
            else:
                content = response_data["choices"][0]["message"]["content"]

            if content:
                self.history.append({"role": "assistant", "content": content})

                # Keep history manageable
                if len(self.history) > 30:
                    self.history = self.history[:1] + self.history[-28:]

                # Save to Honcho memory
                if self.memory:
                    await self.memory.save(self.current_user_id, text, content)

                return content

        except Exception as e:
            import traceback
            logger.error(f"Chat error: {e}")
            logger.error(traceback.format_exc())

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

            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(response.content)
                mp3_path = f.name

            wav_path = mp3_path.replace('.mp3', '.wav')

            try:
                logger.info(f"Converting {len(response.content)} bytes MP3 to WAV...")
                result = await asyncio.to_thread(
                    subprocess.run,
                    ['ffmpeg', '-y', '-i', mp3_path, '-ar', str(SAMPLE_RATE), '-ac', str(CHANNELS), wav_path],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode != 0:
                    logger.error(f"ffmpeg error: {result.stderr.decode()}")
                    return

                # Play via bridge (SDK)
                try:
                    logger.info("Playing audio via bridge...")
                    with open(wav_path, 'rb') as f:
                        wav_data = f.read()
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            "http://127.0.0.1:9000/play",
                            content=wav_data,
                            timeout=120.0  # Long timeout - bridge blocks until playback finishes
                        )
                        if response.status_code != 200:
                            logger.error(f"Bridge error: {response.status_code}")
                except Exception as e:
                    logger.error(f"Bridge playback failed: {e}")
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

        # Show Telegram bridging status
        if TELEGRAM_RELAY:
            logger.info(f"Telegram relay: {TELEGRAM_RELAY}")
            logger.info(f"  Trigger phrase: '{TELEGRAM_TRIGGER}'")
            logger.info(f"  Active: {self.telegram_active}")

        # Greeting
        greeting = "Hey! I'm ready to chat."
        if self.current_user_id != "anonymous":
            greeting = f"Hey there! Good to see you again."
        await self.speak(greeting)
        await self.post_telegram("reachy", greeting)

        try:
            while True:
                audio = await self.listen()
                if not audio:
                    continue

                text = await self.transcribe(audio)
                if not text:
                    logger.info("(no speech detected)")
                    continue

                logger.info(f"You: {text}")

                # Check for trigger phrase to activate Telegram bridging
                if TELEGRAM_TRIGGER and TELEGRAM_TRIGGER.lower() in text.lower():
                    if not self.telegram_active:
                        self.telegram_active = True
                        logger.info("Telegram bridging ACTIVATED")
                        await self.post_telegram("system", "[Robot mode activated]")

                # Post user message to Telegram
                await self.post_telegram("user", text)

                response = await self.think(text)
                if not response:
                    continue

                logger.info(f"Reachy: {response}")

                # Post Reachy's response to Telegram via relay
                await self.post_telegram("reachy", response)

                await self.speak(response)

        except KeyboardInterrupt:
            logger.info("\nGoodbye!")
            await self.post_telegram("system", "[Robot disconnected]")
            await self.speak("Bye!")
        finally:
            await self.stop()


async def main():
    print("=" * 50)
    print("Reachy Direct Talk (Wireless) - Full Feature Set")
    print("=" * 50)

    # Check required env vars
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
        print(f"Missing required: {', '.join(missing)}")
        print("\nExport them or create .env:")
        print('  export OPENAI_API_KEY="sk-..."')
        print('  export CLAWDBOT_ENDPOINT="http://YOUR_MAC_IP:18789/v1/chat/completions"')
        print('  export CLAWDBOT_TOKEN="your-token"')
        print('  export ELEVENLABS_API_KEY="sk_..."')
        return

    # Show optional features
    print("\nFeatures enabled:")
    print(f"  Honcho Memory: {ENABLE_HONCHO and bool(HONCHO_API_KEY)}")
    print(f"  Face Recognition: {ENABLE_FACE_RECOGNITION}")
    print(f"  Tools: {ENABLE_TOOLS}")
    print(f"  Robot IP: {ROBOT_IP}")
    print(f"  STT: {STT_ENDPOINT} (model: {STT_MODEL})")
    print(f"  Telegram Relay: {TELEGRAM_RELAY or 'disabled'}")

    if ENABLE_HONCHO and not HONCHO_API_KEY:
        print("\n  (Set HONCHO_API_KEY to enable persistent memory)")

    if not TELEGRAM_RELAY:
        print("  (Set TELEGRAM_RELAY to enable Telegram bridging)")

    print()

    conv = WirelessConversation()
    await conv.run()


if __name__ == "__main__":
    asyncio.run(main())
