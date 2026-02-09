"""OpenAI Realtime API client for bidirectional audio streaming."""

import asyncio
import base64
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


MEMORY_TOOLS = [
    {
        "type": "function",
        "name": "recall",
        "description": "Think deeply about what you know about this user.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A natural-language query about the user. Can be as simple or complex as needed.",
                }
            },
            "required": ["question"],
        },
    },
    {
        "type": "function",
        "name": "see",
        "description": "Look through your camera to see what's in front of you. Use this when visual context would help answer a question or when the user asks about something you can see.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "create_conclusion",
        "description": "Permanently save an important fact or observation about the current user to your long-term memory. Use this when you learn something significant - their name, preferences, interests, background, or anything you'd want to remember next time you see them.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "A concise, standalone fact about the user. Should make sense without additional context, e.g. 'Their name is Alice' or 'They are interested in robotics'.",
                }
            },
            "required": ["fact"],
        },
    },
]


class OpenAIRealtimeClient:
    """Client for OpenAI's Realtime API with bidirectional audio streaming."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-realtime-preview",
        input_sample_rate: int = 24000,
        output_sample_rate: int = 24000,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate

        self._client = AsyncOpenAI(api_key=api_key)
        self._connection = None
        self._session_context = None
        self._is_connected = False
        self._is_reconnecting = False
        self._audio_chunks_sent = 0
        self._audio_send_timeout_seconds = 2.0

    async def _force_reconnect(self, reason: str) -> None:
        """Force a disconnect so the agent can reconnect cleanly."""
        logger.warning("Forcing realtime reconnect: %s", reason)
        try:
            await self.disconnect()
        except Exception as exc:
            logger.debug("Realtime disconnect during reconnect failed: %s", exc)

    async def connect(
        self, system_prompt: str, tools: list[dict] | None = None
    ) -> None:
        """Connect to OpenAI Realtime API."""
        logger.debug("Connecting to OpenAI Realtime API...")
        self._session_context = self._client.realtime.connect(model=self.model_name)
        logger.debug("Entering session context...")
        self._connection = await self._session_context.__aenter__()
        logger.debug("Session context entered, configuring...")

        session_config = {
            "type": "realtime",
            "instructions": system_prompt,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": self.input_sample_rate},
                    "transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "en",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "interrupt_response": True,
                    },
                },
                "output": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": self.output_sample_rate,
                    },
                    "voice": "verse",
                },
            },
        }

        if tools:
            session_config["tools"] = tools
            session_config["tool_choice"] = "auto"
            logger.info(f"Registering {len(tools)} tools: {[t['name'] for t in tools]}")

        await self._connection.session.update(session=session_config)

        self._is_connected = True
        logger.info(f"Connected to OpenAI Realtime API with model {self.model_name}")

    async def disconnect(self) -> None:
        """Disconnect from OpenAI Realtime API."""
        logger.debug("Disconnecting from OpenAI Realtime API...")
        self._is_connected = False
        if self._session_context:
            try:
                logger.debug("Exiting session context...")
                await self._session_context.__aexit__(None, None, None)
                logger.debug("Session context exited")
            except Exception as e:
                logger.debug(f"Exception during disconnect: {e}")
            self._session_context = None
            self._connection = None
        logger.info("Disconnected from OpenAI Realtime API")

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to OpenAI."""
        if not self._connection or self._is_reconnecting:
            return

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        try:
            await asyncio.wait_for(
                self._connection.input_audio_buffer.append(audio=audio_b64),
                timeout=self._audio_send_timeout_seconds,
            )
            self._audio_chunks_sent += 1
        except asyncio.TimeoutError:
            if not self._is_reconnecting:
                await self._force_reconnect("audio send timeout")
        except Exception as e:
            if not self._is_reconnecting:
                logger.warning(f"Failed to send audio: {e}")

    async def receive_responses(self) -> AsyncIterator[tuple[str, bytes | str]]:
        """Receive responses from OpenAI."""
        if not self._connection:
            raise RuntimeError("Not connected to OpenAI Realtime API")

        async for event in self._connection:
            event_type = event.type
            if event_type == "error":
                logger.error(f"OpenAI error: {event}")

            # User started speaking - treat as potential interruption
            if event_type == "input_audio_buffer.speech_started":
                yield ("interrupted", "")

            # User transcript completed
            if event_type == "conversation.item.input_audio_transcription.completed":
                yield ("input_transcript_final", event.transcript)

            # Assistant transcript completed
            if event_type in (
                "response.audio_transcript.done",
                "response.output_audio_transcript.done",
            ):
                yield ("output_transcript_final", event.transcript)

            # Audio delta from assistant
            if event_type in ("response.audio.delta", "response.output_audio.delta"):
                audio_bytes = base64.b64decode(event.delta)
                yield ("audio", audio_bytes)

            # Response complete
            if event_type == "response.done":
                yield ("turn_complete", "")

            # Function call completed
            if event_type == "response.output_item.done":
                item = event.item
                if item and getattr(item, "type", None) == "function_call":
                    yield (
                        "function_call",
                        {
                            "call_id": item.call_id,
                            "name": item.name,
                            "arguments": item.arguments,
                        },
                    )

    async def send_context(self, context_text: str) -> None:
        """Inject context into the conversation via a system message."""
        if not self._connection or not context_text:
            return

        try:
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": context_text}],
                }
            )
            logger.debug("Injected context into conversation")
        except Exception as e:
            logger.debug(f"Failed to inject context: {e}")

    async def send_image(
        self, image_bytes: bytes, text: str = "", trigger_response: bool = True
    ) -> None:
        """Send an image to the conversation, optionally with accompanying text."""
        if not self._connection:
            logger.warning("send_image: no connection")
            return

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{image_b64}"

        content = [{"type": "input_image", "image_url": data_url}]
        if text:
            content.append({"type": "input_text", "text": text})

        try:
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": content,
                }
            )
            logger.debug("Sent image to conversation")

            if trigger_response:
                await self._connection.response.create()
        except Exception as e:
            logger.error(f"Failed to send image: {e}")

    async def send_function_result(self, call_id: str, output: str) -> None:
        """Send function call result back to the model."""
        if not self._connection:
            logger.warning("send_function_result: no connection")
            return

        try:
            await self._connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                }
            )
            logger.debug("Function result item created, triggering response")
            await self._connection.response.create()
            logger.debug("Response triggered after function result")
        except Exception as e:
            logger.error(f"Failed to send function result: {e}")

    async def trigger_response(self) -> None:
        """Trigger the assistant to respond based on current context."""
        if not self._connection:
            return

        try:
            await self._connection.response.create()
            logger.debug("Triggered assistant response")
        except Exception as e:
            logger.warning(f"Failed to trigger response: {e}")

    @property
    def is_connected(self) -> bool:
        return self._is_connected
