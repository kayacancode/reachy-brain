"""Main Reachy agent - Clawdbot brain with ElevenLabs voice."""

import asyncio
import io
import logging
import os

from pydub import AudioSegment

from .bridge_audio import BridgeAudio
from .clawdbot import ClawdbotClient
from .config import SYSTEM_PROMPT, Config
from .memory import ConversationMemory
from .robot import RobotController
from .stt import WhisperSTT
from .tts import ElevenLabsTTS

logger = logging.getLogger(__name__)

# Reachy host for bridge
REACHY_HOST = os.environ.get("REACHY_HOST", "10.0.0.68")


class ReachyAgent:
    """Reachy robot embodying your Clawdbot AI."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()

        # Robot hardware (movement only, no SDK media)
        self.robot = RobotController()

        # Audio via HTTP bridge
        self.audio = BridgeAudio(host=REACHY_HOST)

        # AI components
        self.clawdbot = ClawdbotClient(
            endpoint=self.config.clawdbot_endpoint,
            token=self.config.clawdbot_token,
            model=self.config.clawdbot_model,
        )
        self.stt = WhisperSTT(api_key=self.config.openai_api_key)
        self.tts = ElevenLabsTTS(
            api_key=self.config.elevenlabs_api_key,
            voice_id=self.config.elevenlabs_voice_id,
        )

        # Memory
        self.memory = ConversationMemory(
            api_key=self.config.honcho_api_key,
            workspace_name=self.config.honcho_workspace_name,
        )

        # State
        self._running = False
        self._is_speaking = False
        self._current_user: str = "user"

    async def start(self) -> None:
        """Start all agent components."""
        logger.info("Starting Reachy agent...")

        # Check bridge first
        status = await self.audio.check_status()
        if status:
            logger.info(f"Bridge connected: {status.get('bridge', 'unknown')}")
        else:
            logger.warning("Bridge not responding - audio may not work")

        # Connect to robot for movement
        await self.robot.connect()
        await self.memory.initialize()

        self._running = True
        self.memory.set_active_user(self._current_user)

        # Greet user
        await self._greet_user()

        logger.info("Reachy agent ready!")

    async def stop(self) -> None:
        """Stop all agent components."""
        logger.info("Stopping Reachy agent...")
        self._running = False

        for name, coro in [
            ("Audio", self.audio.close()),
            ("Robot", self.robot.disconnect()),
            ("Memory", self.memory.close()),
            ("Clawdbot", self.clawdbot.close()),
            ("STT", self.stt.close()),
            ("TTS", self.tts.close()),
        ]:
            try:
                await coro
            except Exception as e:
                logger.debug(f"{name} stop: {e}")

    async def _greet_user(self) -> None:
        """Greet the user."""
        try:
            # Get user context from Honcho if available
            context = None
            try:
                context = await self.memory.get_user_briefing(self._current_user)
            except Exception:
                pass

            greeting_prompt = "A user just appeared. Greet them warmly and briefly."
            response = await self.clawdbot.chat(
                greeting_prompt,
                SYSTEM_PROMPT,
                user_context=context,
            )

            await self._speak(response)

        except Exception as e:
            logger.error(f"Failed to greet user: {e}")

    async def _speak(self, text: str) -> None:
        """Convert text to speech and play through robot."""
        if not text:
            return

        self._is_speaking = True
        logger.info(f"Reachy: {text}")

        try:
            # Save to memory
            await self.memory.add_robot_message(text)

            # Generate audio with ElevenLabs (returns MP3)
            audio_mp3 = await self.tts.synthesize(text)
            if not audio_mp3:
                logger.error("TTS failed to generate audio")
                return

            # Convert MP3 to WAV for bridge (16kHz mono - what the SDK expects)
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_mp3))
            audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)

            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_data = wav_buffer.getvalue()

            # Play through bridge
            await self.audio.play(wav_data)

        except Exception as e:
            logger.error(f"Speech failed: {e}")
        finally:
            self._is_speaking = False

    async def _listen_and_respond(self) -> None:
        """Listen for speech, process, and respond."""
        logger.debug("Listening...")

        # Record from bridge - try up to 2 times if first attempt is too quiet
        audio_data = None
        for attempt in range(2):
            audio_data = await self.audio.listen(duration=6.0)  # Longer duration
            if audio_data and len(audio_data) > 500:  # Lower threshold
                break
            await asyncio.sleep(0.5)

        if not audio_data or len(audio_data) < 500:
            return

        # Transcribe - always try even with quiet audio
        transcript = await self.stt.transcribe(audio_data, sample_rate=16000)
        if not transcript:
            logger.debug("No speech detected")
            return

        logger.info(f"User: {transcript}")

        # Save to memory
        await self.memory.add_user_message(transcript)

        # Get context from Honcho
        context = None
        try:
            context = await self.memory.get_rich_context()
        except Exception:
            pass

        # Get response from Clawdbot
        response = await self.clawdbot.chat(
            transcript,
            SYSTEM_PROMPT,
            user_context=context,
        )

        # Speak response
        await self._speak(response)

    async def _conversation_loop(self) -> None:
        """Main conversation loop."""
        while self._running:
            try:
                await self._listen_and_respond()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Conversation loop error: {e}")
                await asyncio.sleep(1.0)

    async def run(self) -> None:
        """Run the main agent loop."""
        await self.start()

        try:
            await self._conversation_loop()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
