"""Vision system for face detection and camera capture.

Uses MediaPipe for face detection and face_recognition for embeddings.
Falls back to HTTP camera for wireless operation.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe imports (optional - falls back to face_recognition)
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    # Not a warning - face_recognition can do detection too

# Face recognition is optional (requires dlib/cmake)
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning("face_recognition not available - user identification disabled")

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
MODEL_PATH = Path("~/.reachy/models/blaze_face_short_range.tflite").expanduser()


@dataclass
class Face:
    """Detected face with bounding box."""

    bbox: tuple[int, int, int, int]  # x, y, width, height

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)


class HTTPCamera:
    """HTTP camera for getting frames from camera server."""

    def __init__(self, robot_ip: str, port: int = 9001):
        self.url = f"http://{robot_ip}:{port}/snapshot"
        self._client = None

    async def _ensure_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=5.0)

    async def get_frame_async(self) -> np.ndarray | None:
        """Get a frame from the robot camera via HTTP."""
        await self._ensure_client()
        try:
            response = await self._client.get(self.url)
            if response.status_code == 200:
                img_array = np.frombuffer(response.content, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                return frame
        except Exception as e:
            logger.debug(f"HTTP camera error: {e}")
        return None

    def get_frame(self) -> np.ndarray | None:
        """Synchronous wrapper for compatibility."""
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                response = client.get(self.url)
                if response.status_code == 200:
                    img_array = np.frombuffer(response.content, dtype=np.uint8)
                    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    return frame
        except Exception as e:
            logger.debug(f"HTTP camera error: {e}")
        return None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


async def _ensure_model() -> Path:
    """Download the face detection model if not present."""
    if MODEL_PATH.exists():
        return MODEL_PATH

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    import httpx

    logger.info(f"Downloading face detection model to {MODEL_PATH}")
    async with httpx.AsyncClient() as client:
        response = await client.get(MODEL_URL)
        response.raise_for_status()
        MODEL_PATH.write_bytes(response.content)

    return MODEL_PATH


class VisionSystem:
    """Face detection and camera capture system."""

    def __init__(
        self,
        frame_source: Callable[[], np.ndarray | None] | None = None,
        robot_ip: str | None = None,
    ):
        self._frame_source = frame_source
        self._robot_ip = robot_ip
        self._http_camera: HTTPCamera | None = None
        self._face_detector = None
        self._running = False
        self._min_frame_interval_seconds = 0.02

        # Initialize HTTP camera if no frame source and robot_ip provided
        if frame_source is None and robot_ip:
            self._http_camera = HTTPCamera(robot_ip)
            self._frame_source = self._http_camera.get_frame
            logger.info(f"VisionSystem using HTTP camera: {self._http_camera.url}")

    async def start(self) -> None:
        """Start face detection."""
        self._running = True

        if MEDIAPIPE_AVAILABLE:
            model_path = await _ensure_model()
            base_options = mp_tasks.BaseOptions(model_asset_path=str(model_path))
            options = mp_vision.FaceDetectorOptions(
                base_options=base_options,
                min_detection_confidence=0.5,
            )
            self._face_detector = mp_vision.FaceDetector.create_from_options(options)
            logger.info("Vision system started (MediaPipe)")
        elif FACE_RECOGNITION_AVAILABLE:
            logger.info("Vision system started (face_recognition fallback)")
        else:
            logger.warning("Vision system disabled - no face detection available")

    async def stop(self) -> None:
        """Stop and release resources."""
        self._running = False
        if self._face_detector:
            self._face_detector.close()
            self._face_detector = None
        if self._http_camera:
            await self._http_camera.close()
        logger.info("Vision system stopped")

    async def detect_faces(self) -> list[Face]:
        """Detect faces in current frame."""
        if not self._frame_source or not self._face_detector:
            return []

        frame = await asyncio.to_thread(self._frame_source)

        if frame is None:
            return []

        faces = await asyncio.to_thread(self._detect_faces_sync, frame)
        await asyncio.sleep(self._min_frame_interval_seconds)
        return faces

    def _detect_faces_sync(self, frame: np.ndarray) -> list[Face]:
        """Run synchronous face detection on a frame."""
        if not self._face_detector or not MEDIAPIPE_AVAILABLE:
            return []

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._face_detector.detect(mp_image)

        return [
            Face(
                bbox=(
                    d.bounding_box.origin_x,
                    d.bounding_box.origin_y,
                    d.bounding_box.width,
                    d.bounding_box.height,
                )
            )
            for d in result.detections
        ]

    async def capture_frame_jpeg(self, max_size: int = 512) -> bytes | None:
        """Capture current frame as JPEG bytes, resized for efficient transmission."""
        if not self._frame_source:
            return None

        frame = await asyncio.to_thread(self._frame_source)
        if frame is None:
            return None

        return await asyncio.to_thread(self._encode_jpeg, frame, max_size)

    def _encode_jpeg(self, frame: np.ndarray, max_size: int) -> bytes:
        """Resize and encode frame as JPEG."""
        h, w = frame.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        _, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded.tobytes()

    async def get_face_embedding(self) -> np.ndarray | None:
        """Extract face embedding for largest face in frame.

        Uses MediaPipe for detection (reliable) and face_recognition for embeddings.
        Returns None if face_recognition is not available.
        """
        if not FACE_RECOGNITION_AVAILABLE:
            logger.debug("Face recognition not available, skipping embedding")
            return None

        if not self._frame_source:
            return None

        frame = await asyncio.to_thread(self._frame_source)
        if frame is None:
            return None

        # Use MediaPipe for face detection if available
        if self._face_detector and MEDIAPIPE_AVAILABLE:
            faces = await asyncio.to_thread(self._detect_faces_sync, frame)
            if not faces:
                return None

            # Use largest face
            face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
            x, y, w, h = face.bbox

            # Convert MediaPipe bbox (x, y, w, h) to face_recognition format (top, right, bottom, left)
            location = (y, x + w, y + h, x)
            return await asyncio.to_thread(self._extract_embedding_at_location, frame, location)
        else:
            # Fall back to face_recognition's own detection
            return await asyncio.to_thread(self._extract_embedding_auto, frame)

    def _extract_embedding_at_location(self, frame: np.ndarray, location: tuple) -> np.ndarray | None:
        """Extract face embedding at a known location."""
        if not FACE_RECOGNITION_AVAILABLE:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb, [location])
        return encodings[0] if encodings else None

    def _extract_embedding_auto(self, frame: np.ndarray) -> np.ndarray | None:
        """Extract face embedding using face_recognition's built-in detection."""
        if not FACE_RECOGNITION_AVAILABLE:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb)
        return encodings[0] if encodings else None


class FaceIdentityManager:
    """Manages continuous face identification using camera frames."""

    def __init__(self, robot_ip: str | None = None, check_interval: float = 1.0):
        """Initialize with robot IP for HTTP camera.

        Args:
            robot_ip: Robot IP for HTTP camera snapshots.
            check_interval: How often to check for faces (seconds).
        """
        from face_registry import FaceRegistry

        self.registry = FaceRegistry.load()
        self.vision = VisionSystem(robot_ip=robot_ip)
        self.check_interval = check_interval

        self._current_user_id: str | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background face identification."""
        await self.vision.start()
        self._running = True
        self._task = asyncio.create_task(self._identify_loop())
        logger.info("Face identity manager started")

    async def stop(self) -> None:
        """Stop face identification."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.vision.stop()
        logger.info("Face identity manager stopped")

    async def _identify_loop(self) -> None:
        """Continuously identify faces."""
        while self._running:
            try:
                embedding = await self.vision.get_face_embedding()
                user_id = self.registry.identify(embedding)
                self._current_user_id = user_id
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Face identity error: {e}")
                await asyncio.sleep(1.0)

    def get_current_user_id(self) -> str:
        """Get the current identified user ID (or 'anonymous')."""
        return self._current_user_id or "anonymous"

    def list_known_users(self) -> list[str]:
        """List all known user IDs."""
        return self.registry.list_users()
