"""Reachy Mini robot control wrapper."""

import asyncio
import logging
import math
import os
import time

import numpy as np
from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)

# Default Reachy host - can be overridden with REACHY_HOST env var
DEFAULT_REACHY_HOST = "10.0.0.68"


class RobotController:
    """Controls the Reachy Mini robot."""

    def __init__(self, host: str | None = None):
        self._host = host or os.environ.get("REACHY_HOST", DEFAULT_REACHY_HOST)
        self._robot: ReachyMini | None = None
        self._is_connected = False
        self._last_gaze_target: tuple[int, int] | None = None
        self._last_gaze_time: float | None = None
        self._smoothed_gaze_target: tuple[float, float] | None = None
        self._min_gaze_delta_pixels = 25
        self._min_gaze_update_interval = 0.25
        self._gaze_smoothing_alpha = 0.2

    async def connect(self) -> None:
        """Connect to the Reachy Mini robot over network."""
        logger.info("Connecting to Reachy Mini (network mode, no SDK media)...")

        # Run SDK initialization in a separate thread with its own event loop
        # to avoid conflicts with the main asyncio loop
        import concurrent.futures

        def create_robot():
            # Create a new event loop for this thread
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                robot = ReachyMini(
                    connection_mode="network",
                    timeout=10.0,  # Shorter timeout
                    log_level="WARNING",
                    media_backend="no_media",  # Use HTTP bridge for audio instead
                )
                return robot
            except Exception as e:
                logger.warning(f"SDK connection failed: {e}")
                return None

        # Use a thread pool executor
        loop = asyncio.get_event_loop()
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                self._robot = await loop.run_in_executor(executor, create_robot)
        except Exception as e:
            logger.warning(f"SDK connection error: {e}")
            self._robot = None

        if self._robot:
            self._is_connected = True
            # Wake up synchronously since SDK expects its own thread context
            try:
                self._robot.wake_up()
                logger.info("Connected to Reachy Mini and woke up")
            except Exception as e:
                logger.warning(f"Wake up failed: {e}")
        else:
            logger.info("SDK not connected - using bridge only (movement features disabled)")
            self._is_connected = False

    async def disconnect(self) -> None:
        """Disconnect from the robot."""
        if self._robot:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, self._robot.goto_sleep)
            except Exception:
                pass

            try:
                self._robot.media.close()
                self._robot.client.disconnect()
            except Exception:
                pass

            self._robot = None
            self._is_connected = False
            self._last_gaze_target = None
            self._last_gaze_time = None
            self._smoothed_gaze_target = None
            logger.info("Disconnected from Reachy Mini")

    async def look_at_face(self, face_center: tuple[int, int]) -> None:
        """Lock gaze onto a face."""
        if not self._robot:
            return

        u, v = face_center
        if self._smoothed_gaze_target is None:
            smoothed_u, smoothed_v = float(u), float(v)
        else:
            last_u, last_v = self._smoothed_gaze_target
            alpha = self._gaze_smoothing_alpha
            smoothed_u = alpha * u + (1 - alpha) * last_u
            smoothed_v = alpha * v + (1 - alpha) * last_v

        self._smoothed_gaze_target = (smoothed_u, smoothed_v)
        target_u, target_v = int(round(smoothed_u)), int(round(smoothed_v))

        if self._last_gaze_target is not None:
            last_u, last_v = self._last_gaze_target
            if (
                math.hypot(target_u - last_u, target_v - last_v)
                < self._min_gaze_delta_pixels
            ):
                return

        now = time.monotonic()
        if (
            self._last_gaze_time is not None
            and now - self._last_gaze_time < self._min_gaze_update_interval
        ):
            return

        self._last_gaze_target = (target_u, target_v)
        self._last_gaze_time = now
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._robot.look_at_image(target_u, target_v, duration=0.15),
            )
        except Exception as e:
            logger.debug(f"Gaze command failed: {e}")

    def get_camera_frame(self) -> np.ndarray | None:
        """Get the current camera frame."""
        if not self._robot:
            return None
        return self._robot.media.get_frame()

    @property
    def is_connected(self) -> bool:
        return self._is_connected
