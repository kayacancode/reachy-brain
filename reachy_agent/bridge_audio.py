"""Audio via HTTP bridge - simpler than SDK media for wireless."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

REACHY_HOST = os.environ.get("REACHY_HOST", "10.0.0.68")
BRIDGE_PORT = 9000


class BridgeAudio:
    """Audio I/O via HTTP bridge running on Reachy."""

    def __init__(self, host: str = REACHY_HOST, port: int = BRIDGE_PORT):
        self.base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(timeout=30.0)
        self._is_speaking = False

    async def listen(self, duration: float = 3.0) -> bytes | None:
        """Record audio from Reachy's microphone.

        Args:
            duration: Recording duration in seconds

        Returns:
            WAV audio bytes or None if failed
        """
        try:
            url = f"{self.base_url}/listen?duration={duration}"
            response = await self._client.get(url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Bridge listen failed: {e}")
            return None

    async def play(self, audio_data: bytes) -> bool:
        """Play audio through Reachy's speaker.

        Args:
            audio_data: WAV audio bytes

        Returns:
            True if successful
        """
        self._is_speaking = True
        try:
            url = f"{self.base_url}/play"
            response = await self._client.post(
                url,
                content=audio_data,
                headers={"Content-Type": "audio/wav"},
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Bridge play failed: {e}")
            return False
        finally:
            self._is_speaking = False

    async def check_status(self) -> dict | None:
        """Check bridge status."""
        try:
            response = await self._client.get(f"{self.base_url}/status")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Bridge status failed: {e}")
            return None

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    async def close(self) -> None:
        await self._client.aclose()
