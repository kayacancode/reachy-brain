"""Vision module for face detection."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

# Face recognition is optional (requires dlib/cmake)
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

logger = logging.getLogger(__name__)

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
    """Face detection for robot gaze tracking."""

    def __init__(self, frame_source: Callable[[], np.ndarray | None] | None = None):
        self._frame_source = frame_source
        self._face_detector: mp_vision.FaceDetector | None = None
        self._running = False
        self._min_frame_interval_seconds = 0.02

    async def start(self) -> None:
        """Start face detection."""
        model_path = await _ensure_model()

        base_options = mp_tasks.BaseOptions(model_asset_path=str(model_path))
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.5,
        )
        self._face_detector = mp_vision.FaceDetector.create_from_options(options)
        self._running = True
        logger.info("Vision system started")

    async def stop(self) -> None:
        """Stop and release resources."""
        self._running = False
        if self._face_detector:
            self._face_detector.close()
            self._face_detector = None
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
        """Run synchronous face detection on a frame and return results."""
        if not self._face_detector:
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

        Uses MediaPipe for detection (more reliable) and face_recognition for embeddings.
        Returns None if face_recognition is not available.
        """
        if not FACE_RECOGNITION_AVAILABLE:
            logger.debug("Face recognition not available, skipping embedding")
            return None

        if not self._frame_source or not self._face_detector:
            return None

        frame = await asyncio.to_thread(self._frame_source)
        if frame is None:
            return None

        # Use MediaPipe for face detection (same as gaze tracking, known to work)
        faces = await asyncio.to_thread(self._detect_faces_sync, frame)
        if not faces:
            return None

        # Use largest face
        face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        x, y, w, h = face.bbox

        # Convert MediaPipe bbox (x, y, w, h) to face_recognition format (top, right, bottom, left)
        location = (y, x + w, y + h, x)
        return await asyncio.to_thread(self._extract_embedding_at_location, frame, location)

    def _extract_embedding_at_location(self, frame: np.ndarray, location: tuple) -> np.ndarray | None:
        """Extract face embedding at a known location."""
        if not FACE_RECOGNITION_AVAILABLE:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(rgb, [location])
        return encodings[0] if encodings else None
