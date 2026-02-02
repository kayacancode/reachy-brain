#!/usr/bin/env python3
"""
Train custom wake word model for Reachy Mini voice assistant.
Uses OpenWakeWord training to create personalized wake word detection.

Usage:
    # 1. Create samples directory and record 5-10 samples saying your wake word
    mkdir -p samples/openclaw
    # Record samples... (or use record_samples.py helper)

    # 2. Train the model
    python train_wake_word.py --bot-name OpenClaw --samples samples/openclaw/

    # 3. Test the model
    python voice_loop.py --wake-word --local-mic
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def record_sample(output_path: str, duration: float = 2.0):
    """Record a single audio sample using sox/rec."""
    print(f"Recording {duration}s... Speak now!")
    try:
        # Try sox/rec first
        result = subprocess.run([
            "rec", "-r", "16000", "-c", "1", "-b", "16",
            output_path, "trim", "0", str(duration)
        ], capture_output=True, timeout=duration + 5)

        if result.returncode == 0:
            print(f"✓ Recorded: {output_path}")
            return True
    except FileNotFoundError:
        pass

    # Fallback to ffmpeg with avfoundation (macOS)
    try:
        result = subprocess.run([
            "ffmpeg", "-f", "avfoundation", "-i", ":0",
            "-ar", "16000", "-ac", "1",
            "-t", str(duration), "-y", output_path
        ], capture_output=True, timeout=duration + 5)

        if result.returncode == 0:
            print(f"✓ Recorded: {output_path}")
            return True
    except FileNotFoundError:
        print("✗ Error: Neither sox nor ffmpeg found")
        print("  Install with: brew install sox ffmpeg")
        return False

    return False


def record_samples(bot_name: str, output_dir: Path, count: int = 10):
    """Record multiple wake word samples."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nRecording {count} samples for wake word: 'Hey {bot_name}'")
    print("=" * 60)
    print("Tips:")
    print("  - Say the wake word clearly and naturally")
    print("  - Vary your tone and speed slightly")
    print("  - Record in different locations if possible")
    print("  - Wait for the countdown before speaking")
    print("=" * 60)

    samples = []
    for i in range(count):
        print(f"\nSample {i+1}/{count}")
        input("Press Enter when ready... ")

        # Countdown
        for j in range(3, 0, -1):
            print(f"  {j}...")
            time.sleep(0.8)

        # Record
        output_path = str(output_dir / f"sample_{i+1:02d}.wav")
        if record_sample(output_path, duration=2.0):
            samples.append(output_path)
        else:
            print("✗ Failed to record sample")

    print(f"\n✓ Recorded {len(samples)}/{count} samples")
    return samples


def train_custom_wake_word(bot_name: str, samples_dir: Path, output_path: Path = None):
    """
    Train custom wake word model from audio samples.

    Args:
        bot_name: Name of the bot (e.g., "OpenClaw")
        samples_dir: Directory containing positive wake word samples (.wav files)
        output_path: Output path for trained model (.onnx file)
    """
    if output_path is None:
        # Default output path
        output_dir = Path.home() / ".config" / "reachy-brain" / "wake_words"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{bot_name.lower()}.onnx"

    print(f"\nTraining wake word model for '{bot_name}'")
    print("=" * 60)
    print(f"Samples directory: {samples_dir}")
    print(f"Output model: {output_path}")
    print("=" * 60)

    # Check if samples directory exists and has files
    if not samples_dir.exists():
        print(f"✗ Error: Samples directory not found: {samples_dir}")
        return False

    wav_files = list(samples_dir.glob("*.wav"))
    if not wav_files:
        print(f"✗ Error: No .wav files found in {samples_dir}")
        print("  Please record samples first with:")
        print(f"    python {__file__} --bot-name {bot_name} --record")
        return False

    print(f"\nFound {len(wav_files)} sample(s)")
    if len(wav_files) < 5:
        print("⚠ Warning: Fewer than 5 samples. Recommended: 10+ for best accuracy")

    # Train using OpenWakeWord
    try:
        from openwakeword import train
        print("\n📚 Training model... (this may take a few minutes)")

        # Note: OpenWakeWord's train module may have different API
        # This is a simplified example - actual implementation may vary
        train.train_custom_model(
            positive_samples_dir=str(samples_dir),
            output_path=str(output_path),
            epochs=10,
            batch_size=8
        )

        print(f"\n✓ Model trained successfully!")
        print(f"  Model saved to: {output_path}")
        print(f"\nTo use this model:")
        print(f"  1. Update config.json:")
        print(f'     "wake_word": {{ "bot_name": "{bot_name}", ... }}')
        print(f"  2. Run: python voice_loop.py --wake-word")
        return True

    except ImportError:
        print("\n✗ Error: OpenWakeWord training module not found")
        print("  Install with: pip install openwakeword")
        print("\nAlternative: Use pre-trained models")
        print("  Set environment variable: export WAKE_WORD_MODEL='alexa'")
        return False
    except AttributeError:
        print("\n⚠ OpenWakeWord training API may have changed")
        print("  Please refer to: https://github.com/dscripka/openWakeWord")
        print("\nFor now, you can use pre-trained models:")
        print("  - alexa")
        print("  - hey_jarvis")
        print("  Set with: export WAKE_WORD_MODEL='alexa'")
        return False
    except Exception as e:
        print(f"\n✗ Training error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Train custom wake word model for Reachy Mini",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Record samples interactively
  python train_wake_word.py --bot-name OpenClaw --record

  # Train from existing samples
  python train_wake_word.py --bot-name OpenClaw --samples samples/openclaw/

  # Train with custom output path
  python train_wake_word.py --bot-name OpenClaw --samples samples/openclaw/ --output my_model.onnx
        """
    )

    parser.add_argument(
        "--bot-name",
        required=True,
        help="Name of your bot (e.g., 'OpenClaw', 'Reachy')"
    )

    parser.add_argument(
        "--record",
        action="store_true",
        help="Record wake word samples interactively"
    )

    parser.add_argument(
        "--samples",
        type=Path,
        help="Directory containing wake word samples (.wav files at 16kHz)"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for trained model (.onnx file). Default: ~/.config/reachy-brain/wake_words/{bot_name}.onnx"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of samples to record (default: 10)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.record:
        # Record samples mode
        if not args.samples:
            args.samples = Path(f"samples/{args.bot_name.lower()}")

        samples = record_samples(args.bot_name, args.samples, args.count)

        if not samples:
            print("\n✗ No samples recorded")
            return 1

        # Ask if user wants to train now
        print("\n" + "=" * 60)
        response = input("Train model now? [Y/n]: ").strip().lower()
        if response in ('', 'y', 'yes'):
            success = train_custom_wake_word(args.bot_name, args.samples, args.output)
            return 0 if success else 1
        else:
            print(f"\nSamples saved to: {args.samples}")
            print(f"Train later with:")
            print(f"  python {__file__} --bot-name {args.bot_name} --samples {args.samples}")
            return 0

    elif args.samples:
        # Train from existing samples
        success = train_custom_wake_word(args.bot_name, args.samples, args.output)
        return 0 if success else 1

    else:
        parser.print_help()
        print("\n✗ Error: Either --record or --samples required")
        return 1


if __name__ == "__main__":
    sys.exit(main())
