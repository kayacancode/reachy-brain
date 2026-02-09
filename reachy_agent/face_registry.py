"""Face identity registry for multi-user recognition."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path("~/.reachy/face_registry.json").expanduser()
MATCH_THRESHOLD = 0.6  # L2 distance (lower = stricter)
MAX_EMBEDDINGS_PER_USER = 10  # Store multiple embeddings for robustness
NEW_USER_CONSECUTIVE_MISSES = 3  # Require N misses before creating a new user


@dataclass
class RegisteredFace:
    user_id: str
    embeddings: list[np.ndarray]

    @property
    def embedding(self) -> np.ndarray:
        """Primary embedding (first stored)."""
        return self.embeddings[0]

    def best_distance(self, embedding: np.ndarray) -> float:
        """Return the minimum L2 distance across all stored embeddings."""
        return min(np.linalg.norm(embedding - e) for e in self.embeddings)

    def add_embedding(self, embedding: np.ndarray) -> None:
        """Add an embedding, dropping the oldest if at capacity."""
        if len(self.embeddings) >= MAX_EMBEDDINGS_PER_USER:
            self.embeddings.pop(0)
        self.embeddings.append(embedding)


@dataclass
class FaceRegistry:
    _faces: list[RegisteredFace] = field(default_factory=list)
    _last_identified_user: str | None = None
    _consecutive_misses: int = 0
    _last_miss_embedding: np.ndarray | None = None

    @classmethod
    def load(cls) -> "FaceRegistry":
        """Load from disk or create empty."""
        registry = cls()
        if REGISTRY_PATH.exists():
            try:
                data = json.loads(REGISTRY_PATH.read_text())
                for entry in data.get("faces", []):
                    # Support both old (single embedding) and new (list) format
                    raw = entry.get("embeddings", None)
                    if raw is None:
                        raw = [entry["embedding"]]
                    embeddings = [np.array(e) for e in raw]
                    registry._faces.append(
                        RegisteredFace(
                            user_id=entry["user_id"],
                            embeddings=embeddings,
                        )
                    )
                logger.info(f"Loaded {len(registry._faces)} faces from registry")
            except Exception as e:
                logger.warning(f"Failed to load face registry: {e}")
        return registry

    def save(self) -> None:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "faces": [
                {
                    "user_id": f.user_id,
                    "embeddings": [e.tolist() for e in f.embeddings],
                }
                for f in self._faces
            ]
        }
        REGISTRY_PATH.write_text(json.dumps(data, indent=2))

    def identify(self, embedding: np.ndarray | None) -> str:
        """Return user_id for embedding. Creates new user if unknown."""
        if embedding is None:
            if self._last_identified_user:
                logger.info(f"No face, using last user: {self._last_identified_user}")
                return self._last_identified_user
            logger.info("No face and no last user, creating anonymous user")
            return self._create_new_user(None)

        best_match, best_dist = None, float("inf")
        for face in self._faces:
            dist = face.best_distance(embedding)
            if dist < best_dist:
                best_dist, best_match = dist, face

        if best_match and best_dist < MATCH_THRESHOLD:
            logger.info(f"Matched face to {best_match.user_id} (dist={best_dist:.3f})")
            self._last_identified_user = best_match.user_id
            self._consecutive_misses = 0
            self._last_miss_embedding = None
            # Strengthen the model by accumulating this embedding
            best_match.add_embedding(embedding)
            self.save()
            return best_match.user_id

        # No match - but don't create a new user until we've missed N times
        self._consecutive_misses += 1
        self._last_miss_embedding = embedding
        logger.info(
            f"No match (best={best_dist:.3f}, threshold={MATCH_THRESHOLD}, "
            f"miss {self._consecutive_misses}/{NEW_USER_CONSECUTIVE_MISSES})"
        )

        if self._consecutive_misses >= NEW_USER_CONSECUTIVE_MISSES:
            self._consecutive_misses = 0
            return self._create_new_user(embedding)

        # Not enough misses yet - stick with the last known user
        if self._last_identified_user:
            logger.info(f"Below miss threshold, keeping last user: {self._last_identified_user}")
            return self._last_identified_user
        return self._create_new_user(embedding)

    def _create_new_user(self, embedding: np.ndarray | None) -> str:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        if embedding is not None:
            self._faces.append(RegisteredFace(user_id, [embedding]))
            self.save()
            logger.info(f"Registered new face: {user_id}")
        self._last_identified_user = user_id
        self._last_miss_embedding = None
        return user_id
