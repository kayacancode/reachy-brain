"""HTTP-based camera frame source for remote access.

Fetches camera frames from the bridge's /snapshot endpoint,
allowing face recognition to work when running from macOS.
"""

import logging
import os

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)


class HTTPCamera:
    """Fetch camera frames via HTTP from the robot's bridge."""

    def __init__(self, robot_ip: str | None = None, port: int = 9000):
        """Initialize HTTP camera.

        Args:
            robot_ip: Robot IP address. Defaults to ROBOT_IP env var or 192.168.23.66.
            port: Bridge port. Defaults to 9000.
        """
        if robot_ip is None:
            robot_ip = os.getenv("ROBOT_IP", "192.168.23.66")
        self.url = f"http://{robot_ip}:{port}/snapshot"
        self._client = httpx.Client(timeout=2.0)
        logger.info(f"HTTPCamera initialized: {self.url}")

    def get_frame(self) -> np.ndarray | None:
        """Fetch current camera frame as BGR numpy array.

        Returns:
            Frame as numpy array (BGR format) or None if unavailable.
        """
        try:
            resp = self._client.get(self.url)
            if resp.status_code == 200:
                arr = np.frombuffer(resp.content, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return frame
            else:
                logger.debug(f"Snapshot failed: {resp.status_code}")
        except httpx.TimeoutException:
            logger.debug("Snapshot timeout")
        except Exception as e:
            logger.debug(f"Snapshot error: {e}")
        return None

    def close(self) -> None:
        """Close HTTP client."""
        self._client.close()
