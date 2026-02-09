"""Speech-to-text using OpenAI Whisper."""

import io
import logging
import wave

import httpx

logger = logging.getLogger(__name__)


class WhisperSTT:
    """OpenAI Whisper speech-to-text client."""

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=30.0)

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str | None:
        """Transcribe audio to text.

        Args:
            audio_data: Raw PCM audio bytes (int16)
            sample_rate: Sample rate of the audio

        Returns:
            Transcribed text or None if failed/empty
        """
        if not audio_data or len(audio_data) < 500:  # Lower threshold - let Whisper decide
            return None

        # Convert raw PCM to WAV format
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data)
        wav_buffer.seek(0)

        url = "https://api.openai.com/v1/audio/transcriptions"

        headers = {"Authorization": f"Bearer {self.api_key}"}

        files = {
            "file": ("audio.wav", wav_buffer, "audio/wav"),
            "model": (None, self.model),
            "language": (None, "en"),
            "response_format": (None, "text"),
        }

        try:
            response = await self._client.post(url, headers=headers, files=files)
            response.raise_for_status()

            text = response.text.strip()

            # Filter out common Whisper hallucinations (very short/empty)
            if text.lower() in ["", "you"]:
                return None

            return text

        except httpx.HTTPStatusError as e:
            logger.error(f"Whisper API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Whisper error: {e}")
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
