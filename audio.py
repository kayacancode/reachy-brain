"""Audio input/output handling using Reachy Mini's built-in audio system."""

import asyncio
import logging
from typing import AsyncIterator

import numpy as np
from scipy.signal import resample

logger = logging.getLogger(__name__)


def audio_to_int16(audio: np.ndarray) -> np.ndarray:
    """Convert audio to int16 format, handling both float and int inputs."""
    if audio.dtype == np.int16:
        return audio
    if audio.dtype in (np.float32, np.float64):
        return (audio * 32767).astype(np.int16)
    return audio.astype(np.int16)


def audio_to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert audio to float32 format, handling both float and int inputs."""
    if audio.dtype == np.float32:
        return audio
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32767.0
    return audio.astype(np.float32)


class AudioStream:
    """Manages audio input/output through Reachy Mini's media system."""

    def __init__(
        self,
        robot_controller=None,
        input_sample_rate: int = 24000,  # OpenAI Realtime uses 24kHz
        output_sample_rate: int = 24000,  # OpenAI Realtime uses 24kHz
    ):
        self._robot = robot_controller
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate

        self._is_speaking = False
        self._stop_speaking_event = asyncio.Event()
        self._running = False
        self._audio_read_timeout_seconds = 1.0
        self._empty_read_count = 0
        self._max_empty_reads = 25
        self._empty_read_sleep_seconds = 0.02

    async def _read_audio_sample(self, media) -> np.ndarray | bytes | None:
        """Read one audio sample with timeout protection."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(media.get_audio_sample),
                timeout=self._audio_read_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Audio input stalled, restarting recording stream")
            await self._restart_audio_input(media)
            return None
        except Exception as exc:
            logger.error(f"Audio input read failed: {exc}")
            return None

    async def _restart_audio_input(self, media) -> None:
        """Restart the audio recording stream after a stall."""
        try:
            await asyncio.to_thread(media.stop_recording)
        except Exception as exc:
            logger.debug(f"Audio stop_recording failed: {exc}")
        try:
            await asyncio.to_thread(media.start_recording)
        except Exception as exc:
            logger.warning(f"Audio start_recording failed: {exc}")

    async def start(self) -> None:
        """Start audio streams via robot's media system."""
        if not self._robot or not self._robot._robot:
            logger.warning("Robot not connected, audio will not work")
            return

        media = self._robot._robot.media

        # Start recording from robot's microphone
        media.start_recording()
        # Start playback stream
        media.start_playing()

        self._running = True

    async def stop(self) -> None:
        """Stop audio streams."""
        self._running = False

        if self._robot and self._robot._robot:
            media = self._robot._robot.media
            media.stop_recording()
            media.stop_playing()

    async def read_audio(self) -> bytes | None:
        """Read audio from the robot's microphone.

        Uses the same simple approach as the working reachy_mini_conversation_app:
        - Take channel 0 for mono
        - Resample with scipy.signal.resample (higher quality)
        - Convert to int16
        - No gain boost or clipping
        """
        if not self._robot or not self._robot._robot:
            return None

        media = self._robot._robot.media

        # Get audio sample from robot
        sample = await self._read_audio_sample(media)

        if sample is None:
            return None

        # Convert to bytes if numpy array
        if isinstance(sample, np.ndarray):
            if sample.size == 0:
                return b""

            # Handle multi-channel: take channel 0 only
            if sample.ndim == 2:
                # Scipy channels last convention - transpose if needed
                if sample.shape[1] > sample.shape[0]:
                    sample = sample.T
                # Take first channel
                if sample.shape[1] > 1:
                    sample = sample[:, 0]

            # Resample if needed (robot sample rate -> API's expected rate)
            robot_rate = media.get_input_audio_samplerate()
            if robot_rate != self.input_sample_rate and robot_rate > 0:
                new_length = int(len(sample) * self.input_sample_rate / robot_rate)
                sample = await asyncio.to_thread(resample, sample, new_length)

            # Convert to int16 PCM
            sample = audio_to_int16(sample)

            return sample.tobytes()

        # Already bytes
        return sample

    async def audio_generator(self) -> AsyncIterator[bytes]:
        """Generate audio chunks from the microphone.

        Simpler approach matching the working reachy_mini_conversation_app:
        just forward frames as they arrive, no manual chunking.
        """

        while self._running:
            try:
                # Skip mic input while robot is speaking (prevent feedback loop)
                if self._is_speaking:
                    await self.read_audio()  # drain buffer
                    await asyncio.sleep(0.02)
                    continue

                chunk = await self.read_audio()
                if not chunk:
                    self._empty_read_count += 1
                    if self._empty_read_count >= self._max_empty_reads:
                        if self._robot and self._robot._robot:
                            await self._restart_audio_input(self._robot._robot.media)
                        self._empty_read_count = 0
                    await asyncio.sleep(self._empty_read_sleep_seconds)
                    continue

                self._empty_read_count = 0
                yield chunk
            except Exception as e:
                logger.error(f"Error reading audio: {e}")
                await asyncio.sleep(0.1)

    async def play_audio(self, audio_data: bytes) -> None:
        """Play audio data through the robot's speaker."""
        if not self._robot or not self._robot._robot:
            logger.warning("Robot not connected, cannot play audio")
            return

        media = self._robot._robot.media
        self._is_speaking = True
        self._stop_speaking_event.clear()

        try:
            # Convert bytes to numpy float32 array
            audio_array = audio_to_float32(np.frombuffer(audio_data, dtype=np.int16))

            # Resample if needed (API's 24kHz -> robot's output rate)
            robot_out_rate = media.get_output_audio_samplerate()
            if robot_out_rate != self.output_sample_rate and robot_out_rate > 0:
                new_length = int(
                    len(audio_array) * robot_out_rate / self.output_sample_rate
                )
                audio_array = await asyncio.to_thread(resample, audio_array, new_length)
                audio_array = audio_array.astype(np.float32)

            # Play in chunks to allow interruption
            chunk_samples = 480  # ~20ms at 24kHz for faster barge-in
            loop = asyncio.get_event_loop()

            for i in range(0, len(audio_array), chunk_samples):
                if self._stop_speaking_event.is_set():
                    logger.debug("Speech interrupted")
                    break

                chunk = audio_array[i : i + chunk_samples]
                await loop.run_in_executor(None, media.push_audio_sample, chunk)

                # Small yield to allow other tasks
                await asyncio.sleep(0.001)

        except Exception as e:
            logger.error(f"Error playing audio: {e}")
        finally:
            self._is_speaking = False

    def interrupt_speech(self) -> None:
        """Interrupt any ongoing speech playback."""
        if self._is_speaking:
            self._stop_speaking_event.set()

    @property
    def is_speaking(self) -> bool:
        """Return whether audio playback is currently active."""
        return self._is_speaking
