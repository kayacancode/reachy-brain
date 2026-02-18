#!/usr/bin/env python3
"""Face enrollment CLI for personalized Honcho sessions.

Captures your face via camera and registers it with a custom user ID,
so Reachy recognizes you and uses your personal Honcho session.

Usage:
    python3 enroll_face.py --name kaya
    python3 enroll_face.py --name kaya --robot-ip 10.0.0.68
    python3 enroll_face.py --list
    python3 enroll_face.py --delete kaya

Requires:
    - camera_server.py running on the robot (port 9001)
    - face_recognition library installed
"""

import argparse
import logging
import sys
import time

import cv2
import httpx
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check for face_recognition
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.error("face_recognition not installed. Install with: pip install face_recognition")


def get_robot_ip() -> str:
    """Get robot IP from config or default."""
    import os
    from pathlib import Path

    # Check config file
    config_path = Path("~/.reachy-brain/config.env").expanduser()
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.startswith("ROBOT_IP="):
                return line.split("=", 1)[1].strip().strip('"')

    # Fallback to environment
    return os.environ.get("ROBOT_IP", "127.0.0.1")


def capture_frame(robot_ip: str, port: int = 9001) -> np.ndarray | None:
    """Capture a frame from the robot camera via HTTP."""
    url = f"http://{robot_ip}:{port}/snapshot"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                img_array = np.frombuffer(response.content, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                return frame
            else:
                logger.error(f"Camera returned status {response.status_code}")
    except httpx.ConnectError:
        logger.error(f"Cannot connect to camera at {url}")
        logger.error("Make sure camera_server.py is running on the robot")
    except Exception as e:
        logger.error(f"Camera error: {e}")
    return None


def extract_embedding(frame: np.ndarray) -> np.ndarray | None:
    """Extract face embedding from a frame.

    Tries multiple preprocessing approaches to maximize detection success,
    especially for low-light conditions.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return None

    # For low-light images, boost brightness significantly
    # This is the key to detecting faces in dark rooms
    brightness = frame.mean()
    logger.debug(f"Frame brightness: {brightness:.1f}/255")

    if brightness < 100:
        # Super boost for dark images
        alpha = 3.0  # Strong contrast
        beta = 100   # Strong brightness
        frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)
        logger.debug(f"Boosted to: {frame.mean():.1f}/255")

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)
    if encodings:
        return encodings[0]

    # Try with upsampling for smaller/distant faces
    locations = face_recognition.face_locations(rgb, number_of_times_to_upsample=1)
    if locations:
        encodings = face_recognition.face_encodings(rgb, locations)
        if encodings:
            return encodings[0]

    return None


def enroll_face(name: str, robot_ip: str, num_samples: int = 3) -> bool:
    """Enroll a face with the given name.

    Captures multiple samples for robustness.

    Args:
        name: User ID to register (e.g., "kaya")
        robot_ip: Robot IP address
        num_samples: Number of face samples to capture

    Returns:
        True if enrollment succeeded
    """
    if not FACE_RECOGNITION_AVAILABLE:
        logger.error("face_recognition not available")
        return False

    from face_registry import FaceRegistry

    registry = FaceRegistry.load()

    print(f"\n{'='*50}")
    print(f"Face Enrollment for: {name}")
    print(f"{'='*50}")
    print(f"Robot camera: http://{robot_ip}:9001")
    print(f"Samples to capture: {num_samples}")
    print()
    print("Position your face in front of the camera.")
    print("Move slightly between captures for better recognition.")
    print()

    embeddings_captured = 0

    for i in range(num_samples):
        input(f"Press Enter to capture sample {i+1}/{num_samples}...")

        # Capture frame
        print("Capturing...", end=" ", flush=True)
        frame = capture_frame(robot_ip)

        if frame is None:
            print("FAILED - no frame")
            continue

        # Extract embedding
        embedding = extract_embedding(frame)

        if embedding is None:
            print("FAILED - no face detected")
            print("  Make sure your face is visible and well-lit")
            continue

        # Register this embedding
        registry.register_user(name, embedding)
        embeddings_captured += 1
        print(f"OK - face captured!")

        # Small delay between captures
        if i < num_samples - 1:
            time.sleep(0.5)

    print()
    if embeddings_captured > 0:
        print(f"Enrolled {name} with {embeddings_captured} sample(s)")
        print(f"Registry saved to: ~/.reachy/face_registry.json")
        print()
        print("Now when you run talk_wireless.py, you'll be recognized as:")
        print(f"  User ID: {name}")
        print(f"  Honcho session: reachy-mini-{name}")
        return True
    else:
        print("Enrollment failed - no faces captured")
        return False


def list_users():
    """List all enrolled users."""
    from face_registry import FaceRegistry

    registry = FaceRegistry.load()
    users = registry.list_users()

    print(f"\n{'='*50}")
    print("Enrolled Users")
    print(f"{'='*50}")

    if not users:
        print("No users enrolled yet.")
        print("Use: python3 enroll_face.py --name YOUR_NAME")
    else:
        for user_id in users:
            # Find the face to get embedding count
            for face in registry._faces:
                if face.user_id == user_id:
                    print(f"  - {user_id} ({len(face.embeddings)} embedding(s))")
                    break
    print()


def delete_user(name: str) -> bool:
    """Delete an enrolled user."""
    from face_registry import FaceRegistry

    registry = FaceRegistry.load()

    if name not in registry.list_users():
        print(f"User '{name}' not found in registry")
        return False

    confirm = input(f"Delete user '{name}'? [y/N]: ")
    if confirm.lower() != 'y':
        print("Cancelled")
        return False

    registry.delete_user(name)
    print(f"Deleted user: {name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Enroll your face for personalized Reachy/Honcho sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Enroll your face:
    python3 enroll_face.py --name kaya

  Enroll with specific robot IP:
    python3 enroll_face.py --name kaya --robot-ip 10.0.0.68

  Capture more samples for better accuracy:
    python3 enroll_face.py --name kaya --samples 5

  List enrolled users:
    python3 enroll_face.py --list

  Delete a user:
    python3 enroll_face.py --delete kaya
"""
    )

    parser.add_argument(
        "--name", "-n",
        help="User ID to register (e.g., 'kaya')"
    )
    parser.add_argument(
        "--robot-ip", "-r",
        default=None,
        help="Robot IP address (default: from config or 127.0.0.1)"
    )
    parser.add_argument(
        "--samples", "-s",
        type=int,
        default=3,
        help="Number of face samples to capture (default: 3)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all enrolled users"
    )
    parser.add_argument(
        "--delete", "-d",
        metavar="NAME",
        help="Delete an enrolled user"
    )

    args = parser.parse_args()

    # Determine robot IP
    robot_ip = args.robot_ip or get_robot_ip()

    # Handle commands
    if args.list:
        list_users()
        return 0

    if args.delete:
        return 0 if delete_user(args.delete) else 1

    if args.name:
        # Check camera connectivity first
        print(f"Checking camera at http://{robot_ip}:9001...")
        frame = capture_frame(robot_ip)
        if frame is None:
            print("\nCamera not accessible. Make sure:")
            print("  1. Robot is powered on")
            print(f"  2. camera_server.py is running on the robot at {robot_ip}")
            print("  3. You can reach the robot: ping " + robot_ip)
            return 1

        print("Camera OK!")
        return 0 if enroll_face(args.name, robot_ip, args.samples) else 1

    # No command given
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
