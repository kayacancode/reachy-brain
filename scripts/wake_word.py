#!/usr/bin/env python3
"""
Wake word detection for Reachy Mini voice assistant.
Uses OpenWakeWord for dynamic, configurable wake word detection.
"""

import numpy as np
import os
import time
from pathlib import Path


class WakeWordDetector:
    """Detects configurable wake words using OpenWakeWord."""

    def __init__(self,
                 model_path: str = None,
                 threshold: float = 0.5,
                 sample_rate: int = 16000,
                 chunk_size: int = 1280):  # 80ms at 16kHz
        """
        Initialize wake word detector.

        Args:
            model_path: Path to custom wake word model, or pre-trained model name.
                       If None, uses default model from config.
            threshold: Detection threshold (0.0-1.0). Higher = fewer false positives.
            sample_rate: Audio sample rate (must be 16000 for OpenWakeWord).
            chunk_size: Audio chunk size in samples (80ms recommended).
        """
        try:
            from openwakeword.model import Model
            import pyaudio
        except ImportError as e:
            raise ImportError(
                "OpenWakeWord and PyAudio are required for wake word detection.\n"
                "Install with: pip install openwakeword pyaudio\n"
                "On macOS, you may also need: brew install portaudio"
            ) from e

        # Use provided model path or get from environment
        if model_path is None:
            bot_name = os.environ.get("WAKE_WORD_BOT_NAME", "OpenClaw")
            model_dir = Path.home() / ".config" / "reachy-brain" / "wake_words"
            model_path = str(model_dir / f"{bot_name.lower()}.onnx")

            # If custom model doesn't exist, use a pre-trained default
            if not Path(model_path).exists():
                print(f"   Custom wake word model not found: {model_path}")
                print("   Using pre-trained 'alexa' model as fallback")
                print(f"   To train custom model: python scripts/train_wake_word.py --bot-name {bot_name}")
                model_path = "alexa"  # Use pre-trained model

        self.model_path = model_path
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        # Initialize OpenWakeWord model
        print(f"Loading wake word model: {model_path}")
        if isinstance(model_path, str) and not Path(model_path).exists():
            # Pre-trained model name
            self.model = Model(wakeword_models=[model_path])
        else:
            # Custom model file
            self.model = Model(wakeword_models=[str(model_path)])

        # Initialize PyAudio
        self.pyaudio = pyaudio.PyAudio()
        self.stream = None

    def start_listening(self):
        """Start audio stream for wake word detection."""
        if self.stream is not None:
            print("   Warning: Audio stream already active")
            return

        self.stream = self.pyaudio.open(
            format=self.pyaudio.get_format_from_width(2),  # 16-bit
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        print("   Audio stream started")

    def stop_listening(self):
        """Stop audio stream."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.pyaudio:
            self.pyaudio.terminate()
            self.pyaudio = None

    def detect(self) -> tuple[bool, str, float]:
        """
        Process one audio chunk and check for wake word.

        Returns:
            (detected, wake_word, score) tuple:
            - detected: True if wake word detected above threshold
            - wake_word: Name of detected wake word (or None)
            - score: Detection confidence score (0.0-1.0)
        """
        if self.stream is None:
            raise RuntimeError("Audio stream not started. Call start_listening() first.")

        try:
            # Read audio chunk
            audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Process through wake word model
            predictions = self.model.predict(audio_array)

            # Check if any wake word exceeded threshold
            for word, score in predictions.items():
                if score > self.threshold:
                    return True, word, score

            return False, None, 0.0
        except Exception as e:
            print(f"   Detection error: {e}")
            return False, None, 0.0

    def wait_for_wake_word(self, callback=None, timeout=None):
        """
        Continuously listen for wake word until detected or timeout.

        Args:
            callback: Optional function to call when wake word detected.
                     Callback signature: callback(wake_word: str, score: float)
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            (detected, wake_word, score) tuple if wake word detected within timeout,
            or (False, None, 0.0) if timeout reached.
        """
        self.start_listening()

        start_time = time.time()
        try:
            while True:
                detected, wake_word, score = self.detect()

                if detected:
                    print(f"   Wake word '{wake_word}' detected! (score: {score:.2f})")
                    if callback:
                        callback(wake_word, score)
                    return True, wake_word, score

                # Check timeout
                if timeout and (time.time() - start_time) > timeout:
                    print(f"   Wake word detection timeout ({timeout}s)")
                    return False, None, 0.0

                # Small delay to prevent CPU spinning
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\n   Wake word detection interrupted")
            return False, None, 0.0
        finally:
            self.stop_listening()


def test_wake_word():
    """Test wake word detection with default configuration."""
    print("Wake Word Detection Test")
    print("=" * 50)

    # Get configuration from environment
    bot_name = os.environ.get("WAKE_WORD_BOT_NAME", "OpenClaw")
    threshold = float(os.environ.get("WAKE_WORD_THRESHOLD", "0.5"))

    print(f"Bot name: {bot_name}")
    print(f"Threshold: {threshold}")
    print("=" * 50)
    print("\nListening for wake word... (Press Ctrl+C to stop)")
    print(f"Try saying: 'Hey {bot_name}'\n")

    # Initialize detector
    detector = WakeWordDetector(threshold=threshold)

    # Wait for wake word
    detected, wake_word, score = detector.wait_for_wake_word()

    if detected:
        print(f"\n✓ Successfully detected: {wake_word} (score: {score:.2f})")
    else:
        print("\n✗ No wake word detected")


if __name__ == "__main__":
    test_wake_word()
