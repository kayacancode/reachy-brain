"""Clawdbot handler using Whisper STT + Claude LLM + ElevenLabs TTS.

This handler replaces OpenAI Realtime API with a modular stack:
- Speech-to-Text: OpenAI Whisper
- LLM: Clawdbot (Claude via OpenClaw)
- Text-to-Speech: ElevenLabs
- Memory: Honcho for persistent user context
"""

import io
import os
import json
import base64
import asyncio
import logging
from typing import Any, Final, Tuple, Literal
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydub import AudioSegment
from scipy.signal import resample
from fastrtc import AdditionalOutputs, AsyncStreamHandler, wait_for_item, audio_to_int16

from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.tools.core_tools import (
    ToolDependencies,
    get_tool_specs,
    dispatch_tool_call,
)

logger = logging.getLogger(__name__)

# Audio configuration
FASTRTC_SAMPLE_RATE: Final[Literal[24000]] = 24000  # fastrtc default
WHISPER_SAMPLE_RATE: Final[int] = 16000  # Whisper expects 16kHz
ELEVENLABS_OUTPUT_RATE: Final[int] = 44100  # ElevenLabs outputs 44.1kHz MP3


@dataclass
class ClawdbotConfig:
    """Configuration for Clawdbot handler."""

    clawdbot_endpoint: str
    clawdbot_token: str
    clawdbot_model: str
    openai_api_key: str  # For Whisper STT
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    honcho_api_key: str | None
    honcho_workspace: str

    @classmethod
    def from_env(cls) -> "ClawdbotConfig":
        """Load configuration from environment variables."""
        return cls(
            clawdbot_endpoint=os.getenv(
                "CLAWDBOT_ENDPOINT", "http://localhost:18789/v1/chat/completions"
            ),
            clawdbot_token=os.getenv(
                "CLAWDBOT_TOKEN", "REDACTED_CLAWDBOT_TOKEN"
            ),
            clawdbot_model=os.getenv("CLAWDBOT_MODEL", "claude-sonnet-4-20250514"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
            honcho_api_key=os.getenv("HONCHO_API_KEY"),
            honcho_workspace=os.getenv("HONCHO_WORKSPACE_ID", "reachy-mini"),
        )


class ClawdbotHandler(AsyncStreamHandler):
    """Clawdbot handler implementing fastrtc stream interface.

    Uses Whisper STT + Claude (Clawdbot) + ElevenLabs TTS instead of OpenAI Realtime.
    """

    def __init__(
        self,
        config: ClawdbotConfig,
        deps: ToolDependencies,
        gradio_mode: bool = False,
    ):
        """Initialize the handler."""
        super().__init__(
            expected_layout="mono",
            output_sample_rate=FASTRTC_SAMPLE_RATE,
            input_sample_rate=FASTRTC_SAMPLE_RATE,
        )
        self.config = config
        self.deps = deps
        self.gradio_mode = gradio_mode

        # Audio buffers
        self.input_buffer: list[NDArray[np.int16]] = []
        self.output_queue: asyncio.Queue[
            Tuple[int, NDArray[np.int16]] | AdditionalOutputs
        ] = asyncio.Queue()

        # VAD state (simple RMS-based)
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._vad_threshold = 500  # RMS threshold for speech
        self._min_speech_frames = 10  # ~200ms at 50fps
        self._max_silence_frames = 25  # ~500ms silence to end utterance

        # Processing state
        self._processing_lock = asyncio.Lock()
        self._is_processing = False

        # Clients (lazy init in start_up)
        self._stt = None
        self._tts = None
        self._llm = None
        self._memory = None

        # Conversation state
        self._conversation_history: list[dict] = []

        # Tool specs converted to Claude format
        self._tool_specs: list[dict] = []

        # Idle tracking
        self.last_activity_time = 0.0
        self.start_time = 0.0

    def copy(self) -> "ClawdbotHandler":
        """Create a copy of the handler."""
        return ClawdbotHandler(self.config, self.deps, self.gradio_mode)

    async def start_up(self) -> None:
        """Initialize AI service clients."""
        import httpx

        logger.info("Starting ClawdbotHandler...")

        # Initialize Whisper STT client
        self._stt_client = httpx.AsyncClient(timeout=30.0)

        # Initialize ElevenLabs TTS client
        self._tts_client = httpx.AsyncClient(timeout=30.0)

        # Initialize Clawdbot LLM client
        self._llm_client = httpx.AsyncClient(timeout=60.0)

        # Initialize Honcho memory (optional)
        if self.config.honcho_api_key:
            try:
                from honcho import Honcho
                from honcho.api_types import PeerConfig

                self._memory_client = Honcho(
                    api_key=self.config.honcho_api_key,
                    workspace_id=self.config.honcho_workspace,
                )
                # Initialize robot peer
                self._robot_peer = await self._memory_client.aio.peer(
                    "reachy",
                    metadata={"type": "robot", "model": "reachy-mini"},
                    configuration=PeerConfig(observe_me=False),
                )
                self._user_sessions: dict[str, Any] = {}
                self._user_peers: dict[str, Any] = {}
                self._active_user_id = "user"
                logger.info("Honcho memory initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Honcho: {e}")
                self._memory_client = None
        else:
            self._memory_client = None
            logger.info("Honcho memory disabled (no API key)")

        # Convert OpenAI tool specs to Claude format
        self._tool_specs = self._convert_tools_to_claude_format(get_tool_specs())
        logger.info(f"Loaded {len(self._tool_specs)} tools")

        # Initialize timing
        loop = asyncio.get_event_loop()
        self.last_activity_time = loop.time()
        self.start_time = loop.time()

        logger.info("ClawdbotHandler initialized successfully")

    def _convert_tools_to_claude_format(self, openai_specs: list[dict]) -> list[dict]:
        """Convert OpenAI function specs to Claude tool format."""
        claude_tools = []
        for spec in openai_specs:
            claude_tools.append({
                "name": spec["name"],
                "description": spec["description"],
                "input_schema": spec["parameters"],
            })
        return claude_tools

    async def receive(self, frame: Tuple[int, NDArray[np.int16]]) -> None:
        """Receive audio frame and accumulate for VAD."""
        if self._is_processing:
            return  # Skip input while processing response

        sample_rate, audio = frame

        # Reshape if needed (handle stereo)
        if audio.ndim == 2:
            if audio.shape[1] > audio.shape[0]:
                audio = audio.T
            if audio.shape[1] > 1:
                audio = audio[:, 0]
        audio = audio.flatten()

        # Simple RMS-based VAD
        rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))

        if rms > self._vad_threshold:
            self._speech_frames += 1
            self._silence_frames = 0
            if not self._is_speaking and self._speech_frames >= self._min_speech_frames:
                self._is_speaking = True
                self.deps.movement_manager.set_listening(True)
                logger.debug("Speech started")
        else:
            if self._is_speaking:
                self._silence_frames += 1
                if self._silence_frames >= self._max_silence_frames:
                    # End of speech - process accumulated audio
                    self._is_speaking = False
                    self._speech_frames = 0
                    self.deps.movement_manager.set_listening(False)
                    logger.debug("Speech ended, processing...")

                    # Copy buffer and clear
                    audio_to_process = self.input_buffer.copy()
                    self.input_buffer.clear()

                    # Process in background
                    asyncio.create_task(self._process_speech(audio_to_process))

        # Accumulate audio while speaking
        if self._is_speaking or self._silence_frames < self._max_silence_frames:
            self.input_buffer.append(audio)

    async def _process_speech(self, audio_chunks: list[NDArray[np.int16]]) -> None:
        """Process accumulated speech: STT -> Memory -> LLM -> TTS."""
        async with self._processing_lock:
            self._is_processing = True
            try:
                if not audio_chunks:
                    return

                # Combine audio chunks
                audio_data = np.concatenate(audio_chunks)

                # Resample from 24kHz to 16kHz for Whisper
                resampled = resample(
                    audio_data,
                    int(len(audio_data) * WHISPER_SAMPLE_RATE / FASTRTC_SAMPLE_RATE),
                ).astype(np.int16)

                # STT
                transcript = await self._transcribe(resampled.tobytes())
                if not transcript:
                    return

                logger.info(f"User: {transcript}")
                await self.output_queue.put(
                    AdditionalOutputs({"role": "user", "content": transcript})
                )

                # Get Honcho context
                context = await self._get_memory_context() if self._memory_client else None

                # LLM with tool calling
                response, tool_calls = await self._chat_with_tools(transcript, context)

                # Handle tool calls
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
                    logger.info(f"Tool call: {tool_name}({tool_args})")

                    result = await dispatch_tool_call(
                        tool_name, json.dumps(tool_args), self.deps
                    )

                    await self.output_queue.put(
                        AdditionalOutputs({
                            "role": "assistant",
                            "content": json.dumps(result),
                            "metadata": {"title": f"Tool: {tool_name}", "status": "done"},
                        })
                    )

                if response:
                    logger.info(f"Reachy: {response}")
                    await self.output_queue.put(
                        AdditionalOutputs({"role": "assistant", "content": response})
                    )

                    # TTS and queue audio
                    await self._speak(response)

                    # Save to memory
                    if self._memory_client:
                        await self._save_to_memory(transcript, response)

                # Update activity time
                self.last_activity_time = asyncio.get_event_loop().time()

            except Exception as e:
                logger.error(f"Speech processing error: {e}")
            finally:
                self._is_processing = False

    async def _transcribe(self, audio_bytes: bytes) -> str | None:
        """Transcribe audio using Whisper."""
        if not audio_bytes or len(audio_bytes) < 500:
            return None

        # Convert raw PCM to WAV
        import wave

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(WHISPER_SAMPLE_RATE)
            wav.writeframes(audio_bytes)
        wav_buffer.seek(0)

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.config.openai_api_key}"}
        files = {
            "file": ("audio.wav", wav_buffer, "audio/wav"),
            "model": (None, "whisper-1"),
            "language": (None, "en"),
            "response_format": (None, "text"),
        }

        try:
            response = await self._stt_client.post(url, headers=headers, files=files)
            response.raise_for_status()
            text = response.text.strip()

            # Filter hallucinations
            if text.lower() in ["", "you", "thanks", "bye", "thank you"]:
                return None
            return text
        except Exception as e:
            logger.error(f"Whisper error: {e}")
            return None

    async def _get_memory_context(self) -> str | None:
        """Get user context from Honcho memory."""
        if not self._memory_client:
            return None

        try:
            session = await self._get_user_session(self._active_user_id)
            session_context = await session.aio.context(
                tokens=8192, peer_target=self._active_user_id
            )
            return json.dumps({
                "user_representation": session_context.peer_representation,
                "peer_card": session_context.peer_card,
                "recent_messages": session_context.messages,
            }, default=str)
        except Exception as e:
            logger.warning(f"Memory context error: {e}")
            return None

    async def _get_user_session(self, user_id: str) -> Any:
        """Get or create Honcho session for user."""
        if user_id in self._user_sessions:
            return self._user_sessions[user_id]
        session = await self._memory_client.aio.session(f"reachy-chat-{user_id}")
        self._user_sessions[user_id] = session
        return session

    async def _get_user_peer(self, user_id: str) -> Any:
        """Get or create Honcho peer for user."""
        if user_id in self._user_peers:
            return self._user_peers[user_id]
        peer = await self._memory_client.aio.peer(user_id, metadata={"type": "human"})
        self._user_peers[user_id] = peer
        return peer

    async def _chat_with_tools(
        self, user_message: str, context: str | None
    ) -> Tuple[str, list[dict]]:
        """Chat with Clawdbot, handling tool calls."""
        # Build messages
        system_prompt = get_session_instructions()

        messages = [{"role": "system", "content": system_prompt}]

        if context:
            messages.append({
                "role": "system",
                "content": f"[User Context from Memory]\n{context}",
            })

        # Add conversation history
        messages.extend(self._conversation_history)

        # Add current message
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.config.clawdbot_model,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.7,
            "tools": self._tool_specs,
        }

        headers = {
            "Authorization": f"Bearer {self.config.clawdbot_token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._llm_client.post(
                self.config.clawdbot_endpoint,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or not data["choices"]:
                return "I'm having trouble thinking right now.", []

            choice = data["choices"][0]
            message = choice.get("message", {})

            # Extract tool calls
            tool_calls = []
            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    if tc.get("type") == "function":
                        func = tc.get("function", {})
                        tool_calls.append({
                            "name": func.get("name", ""),
                            "arguments": json.loads(func.get("arguments", "{}")),
                        })

            # Extract text response
            content = message.get("content", "")

            # Update conversation history
            self._conversation_history.append({"role": "user", "content": user_message})
            if content:
                self._conversation_history.append({"role": "assistant", "content": content})

            # Keep history manageable
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]

            return content or "", tool_calls

        except Exception as e:
            logger.error(f"Clawdbot error: {e}")
            return "Something went wrong. Let me try again.", []

    async def _speak(self, text: str) -> None:
        """Convert text to speech and queue audio."""
        if not text or not text.strip():
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}"
        headers = {
            "xi-api-key": self.config.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            response = await self._tts_client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            mp3_bytes = response.content

            # Convert MP3 to PCM
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            audio = audio.set_frame_rate(FASTRTC_SAMPLE_RATE).set_channels(1)
            pcm_bytes = audio.raw_data

            # Convert to numpy array
            audio_array = np.frombuffer(pcm_bytes, dtype=np.int16)

            # Feed to head wobbler for speech-reactive motion
            if self.deps.head_wobbler is not None:
                # ElevenLabs returns full audio, convert to base64 chunks for wobbler
                chunk_size = 4096
                for i in range(0, len(pcm_bytes), chunk_size):
                    chunk = pcm_bytes[i : i + chunk_size]
                    self.deps.head_wobbler.feed(base64.b64encode(chunk).decode())

            # Queue audio in chunks matching fastrtc expectations
            chunk_samples = FASTRTC_SAMPLE_RATE // 10  # 100ms chunks
            for i in range(0, len(audio_array), chunk_samples):
                chunk = audio_array[i : i + chunk_samples]
                if len(chunk) > 0:
                    await self.output_queue.put(
                        (FASTRTC_SAMPLE_RATE, chunk.reshape(1, -1))
                    )

        except Exception as e:
            logger.error(f"TTS error: {e}")

    async def _save_to_memory(self, user_message: str, robot_message: str) -> None:
        """Save conversation turn to Honcho memory."""
        if not self._memory_client:
            return

        try:
            session = await self._get_user_session(self._active_user_id)
            user_peer = await self._get_user_peer(self._active_user_id)

            # Save user message
            await session.aio.add_messages(user_peer.message(user_message))

            # Save robot message
            await session.aio.add_messages(self._robot_peer.message(robot_message))

        except Exception as e:
            logger.warning(f"Memory save error: {e}")

    async def emit(self) -> Tuple[int, NDArray[np.int16]] | AdditionalOutputs | None:
        """Emit audio frame to be played by the speaker."""
        return await wait_for_item(self.output_queue)

    async def shutdown(self) -> None:
        """Clean up resources."""
        for client in [self._stt_client, self._tts_client, self._llm_client]:
            if client:
                try:
                    await client.aclose()
                except Exception:
                    pass

        # Clear queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        logger.info("ClawdbotHandler shutdown complete")

    async def apply_personality(self, profile: str | None) -> str:
        """Apply a new personality profile at runtime.

        Unlike OpenAI Realtime, we just need to update the config since
        we fetch instructions fresh on each chat call.
        """
        from reachy_mini_conversation_app.config import set_custom_profile

        set_custom_profile(profile)
        # Clear conversation history to apply new personality
        self._conversation_history.clear()
        return f"Applied personality: {profile or 'default'}"
