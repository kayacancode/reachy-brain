#!/usr/bin/env python3
"""
Reachy Mini Camera — Snapshot & Vision
======================================

Capture images from Reachy Mini's camera via WebRTC or HTTP endpoints.
Adapted from coopergwrenn/clawd-reachy patterns.

Usage:
  python3 camera.py                    # Take a snapshot, save to snapshots/
  python3 camera.py --output photo.jpg # Save to specific file
  python3 camera.py --base64           # Return base64 encoded image

As a module:
  from camera import take_snapshot, get_snapshot_base64
"""

import os
import sys
import time
import base64
import requests
import argparse
from pathlib import Path
from datetime import datetime

# Configuration
REACHY_HOST = os.environ.get('REACHY_HOST', '192.168.23.66')
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"

# Ensure snapshot directory exists
SNAPSHOT_DIR.mkdir(exist_ok=True)


def try_http_snapshot():
    """Try various HTTP endpoints for snapshots."""
    endpoints = [
        f"http://{REACHY_HOST}:8000/camera/snapshot",
        f"http://{REACHY_HOST}:8000/api/camera/snapshot",
        f"http://{REACHY_HOST}:8000/snapshot",
        f"http://{REACHY_HOST}:8080/snapshot",
        f"http://{REACHY_HOST}:8554/snapshot",
        f"http://{REACHY_HOST}:9000/snapshot",  # Bridge might have it
    ]

    for url in endpoints:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')
                if content_type.startswith('image') or len(resp.content) > 1000:
                    return resp.content
        except requests.exceptions.RequestException:
            pass

    return None


def try_webrtc_snapshot():
    """Try to get snapshot via WebRTC stream."""
    try:
        # Check if WebRTC stream is available
        status_url = f"http://{REACHY_HOST}:8000/api/webrtc/status"
        resp = requests.get(status_url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('streaming'):
                # WebRTC is streaming - try to get a frame
                # This would require actual WebRTC client implementation
                # For now, we note it's available but can't easily grab a frame
                print("WebRTC stream is active but frame capture requires SDK")
                return None
    except:
        pass

    return None


def try_sdk_snapshot():
    """
    Try to get snapshot using the Reachy Mini SDK.
    This requires the SDK to be installed and would need to run ON Reachy
    or have network SDK access configured.
    """
    try:
        # This import would only work if SDK is available
        from reachy_mini import ReachyMini

        with ReachyMini(host=REACHY_HOST, timeout=10) as mini:
            frame = mini.media.get_frame()
            if frame is not None:
                import cv2
                # Encode as JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                return buffer.tobytes()
    except ImportError:
        print("Reachy Mini SDK not available locally")
    except Exception as e:
        print(f"SDK snapshot failed: {e}")

    return None


def take_snapshot(output_path=None):
    """
    Take a snapshot from Reachy's camera.

    Args:
        output_path: Path to save the image. If None, generates timestamped filename.

    Returns:
        Path to saved image, or None if failed.
    """
    print(f"Attempting to capture from Reachy Mini at {REACHY_HOST}...")

    # Try HTTP first (fastest if available)
    image_data = try_http_snapshot()

    if not image_data:
        # Try WebRTC
        print("HTTP endpoints not available, trying WebRTC...")
        image_data = try_webrtc_snapshot()

    if not image_data:
        # Try SDK as last resort
        print("Trying SDK method...")
        image_data = try_sdk_snapshot()

    if not image_data:
        print("Could not capture snapshot from any source")
        print("\nCamera access options:")
        print("1. HTTP endpoint (if Reachy has snapshot app installed)")
        print("2. WebRTC stream (requires SDK with GStreamer)")
        print("3. Run this script ON Reachy with SDK access")
        return None

    # Save the image
    if output_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = SNAPSHOT_DIR / f"snap_{timestamp}.jpg"
    else:
        output_path = Path(output_path)

    output_path.write_bytes(image_data)
    print(f"Saved: {output_path}")
    return str(output_path)


def get_snapshot_base64():
    """
    Get a snapshot as base64 encoded string.

    Returns:
        Base64 encoded image string, or None if failed.
    """
    image_data = try_http_snapshot()

    if not image_data:
        image_data = try_webrtc_snapshot()

    if not image_data:
        image_data = try_sdk_snapshot()

    if image_data:
        return base64.b64encode(image_data).decode('utf-8')

    return None


def get_camera_status():
    """Check camera availability status."""
    status = {
        "host": REACHY_HOST,
        "http_available": False,
        "webrtc_available": False,
        "sdk_available": False,
    }

    # Check HTTP endpoints
    for endpoint in ["/camera/snapshot", "/api/camera/snapshot", "/snapshot"]:
        try:
            resp = requests.head(f"http://{REACHY_HOST}:8000{endpoint}", timeout=2)
            if resp.status_code in [200, 405]:  # 405 = method not allowed but endpoint exists
                status["http_available"] = True
                status["http_endpoint"] = endpoint
                break
        except:
            pass

    # Check WebRTC
    try:
        resp = requests.get(f"http://{REACHY_HOST}:8000/api/webrtc/status", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            status["webrtc_available"] = data.get('streaming', False)
    except:
        pass

    # Check SDK
    try:
        from reachy_mini import ReachyMini
        status["sdk_available"] = True
    except ImportError:
        pass

    return status


def main():
    global REACHY_HOST

    parser = argparse.ArgumentParser(description="Capture image from Reachy Mini camera")
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--base64', '-b', action='store_true', help='Output base64 instead of file')
    parser.add_argument('--status', '-s', action='store_true', help='Check camera status')
    parser.add_argument('--host', help=f'Reachy host (default: {REACHY_HOST})')
    args = parser.parse_args()

    if args.host:
        REACHY_HOST = args.host

    if args.status:
        status = get_camera_status()
        print("Camera Status:")
        print(f"  Host: {status['host']}")
        print(f"  HTTP endpoint: {'Yes' if status['http_available'] else 'No'}")
        print(f"  WebRTC stream: {'Yes' if status['webrtc_available'] else 'No'}")
        print(f"  SDK available: {'Yes' if status['sdk_available'] else 'No'}")
        return 0

    if args.base64:
        result = get_snapshot_base64()
        if result:
            print(result)
            return 0
        else:
            print("Failed to capture snapshot", file=sys.stderr)
            return 1

    result = take_snapshot(args.output)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
