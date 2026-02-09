"""Text-to-speech using ElevenLabs."""

import io
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class ElevenLabsTTS:
    """ElevenLabs text-to-speech client."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel
        model_id: str = "eleven_turbo_v2_5",  # Fast model
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self._client = httpx.AsyncClient(timeout=30.0)

    async def synthesize(self, text: str) -> bytes | None:
        """Convert text to speech audio.

        Args:
            text: The text to speak

        Returns:
            Audio bytes (MP3 format) or None if failed
        """
        if not text or not text.strip():
            return None

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        try:
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.content

        except httpx.HTTPStatusError as e:
            logger.error(f"ElevenLabs API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"ElevenLabs error: {e}")
            return None

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Stream audio synthesis for lower latency.

        Yields chunks of audio as they're generated.
        """
        if not text or not text.strip():
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with self._client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    yield chunk

        except Exception as e:
            logger.error(f"ElevenLabs stream error: {e}")

    async def get_voices(self) -> list[dict]:
        """Get available voices."""
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": self.api_key}

        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("voices", [])
        except Exception as e:
            logger.error(f"Failed to get voices: {e}")
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Common voice IDs for reference
VOICE_IDS = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "domi": "AZnzlk1XvdvUeBnXmlld",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "antoni": "ErXwobaYiN019PkySvjV",
    "elli": "MF3mGyEYCl7XYWbV9V6O",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "arnold": "VR6AewLTigWG4xSOukaG",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
}
