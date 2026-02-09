"""Face identity manager - wraps vision.py + face_registry.py for easy integration."""

import asyncio
import logging
import os
import threading
from typing import Any, Callable

import numpy as np

from reachy_mini_conversation_app.vision import VisionSystem
from reachy_mini_conversation_app.face_registry import FaceRegistry

logger = logging.getLogger(__name__)


class FaceIdentityManager:
    """Manages continuous face identification using camera frames."""

    def __init__(self, camera_worker: Any = None, robot_ip: str | None = None):
        """Initialize with camera worker or HTTP fallback.

        Args:
            camera_worker: CameraWorker instance for local SDK access.
            robot_ip: Robot IP for HTTP fallback when camera_worker is None.
        """
        self.camera_worker = camera_worker
        self.registry = FaceRegistry.load()

        # Determine frame source
        frame_source: Callable[[], np.ndarray | None] | None = None

        if camera_worker is not None:
            # Use SDK camera worker (running on robot or with working WebRTC)
            frame_source = camera_worker.get_latest_frame
            logger.info("FaceIdentityManager using SDK camera worker")
        else:
            # Fallback to HTTP snapshots (running from macOS)
            try:
                from reachy_mini_conversation_app.http_camera import HTTPCamera
                http_cam = HTTPCamera(robot_ip=robot_ip)
                frame_source = http_cam.get_frame
                logger.info(f"FaceIdentityManager using HTTP camera: {http_cam.url}")
            except Exception as e:
                logger.warning(f"Failed to initialize HTTP camera: {e}")

        self.vision = VisionSystem(frame_source=frame_source)

        self._current_user_id: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start background face identification."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Face identity manager started")

    def stop(self) -> None:
        """Stop face identification."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Face identity manager stopped")

    def _run_loop(self) -> None:
        """Run async loop in thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._identify_loop())
        finally:
            self._loop.close()

    async def _identify_loop(self) -> None:
        """Continuously identify faces."""
        await self.vision.start()

        while not self._stop_event.is_set():
            try:
                embedding = await self.vision.get_face_embedding()
                user_id = self.registry.identify(embedding)
                self._current_user_id = user_id
                await asyncio.sleep(0.5)  # Check every 500ms
            except Exception as e:
                logger.error(f"Face identity error: {e}")
                await asyncio.sleep(1.0)

        await self.vision.stop()

    def get_current_user_id(self) -> str | None:
        """Get the current identified user ID."""
        return self._current_user_id

    def list_known_users(self) -> list[str]:
        """List all known user IDs."""
        return [f.user_id for f in self.registry._faces]
