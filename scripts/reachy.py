#!/usr/bin/env python3
"""Reachy Mini control script."""

import argparse
import base64
import json
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE_URL = "http://192.168.1.171:8042"


def api_get(path: str) -> dict:
    """GET request to Reachy API."""
    try:
        with urlopen(f"{BASE_URL}{path}", timeout=10) as resp:
            return json.loads(resp.read())
    except URLError as e:
        return {"error": str(e)}


def api_post(path: str, data: dict = None) -> dict:
    """POST request to Reachy API."""
    try:
        req = Request(
            f"{BASE_URL}{path}",
            data=json.dumps(data or {}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except URLError as e:
        return {"error": str(e)}


def cmd_status(args):
    """Get robot status."""
    result = api_get("/api/status")
    print(json.dumps(result, indent=2))


def cmd_state(args):
    """Get full daemon state."""
    result = api_get("/api/daemon_status")
    print(json.dumps(result, indent=2))


def cmd_wake(args):
    """Wake up the robot."""
    result = api_post("/api/wake_up")
    print(json.dumps(result, indent=2))


def cmd_sleep(args):
    """Put robot to sleep."""
    result = api_post("/api/go_to_sleep")
    print(json.dumps(result, indent=2))


def cmd_zero(args):
    """Move to neutral position."""
    result = api_post("/api/go_to_zero")
    print(json.dumps(result, indent=2))


def cmd_head(args):
    """Move head."""
    data = {"duration": args.duration}
    if args.pitch is not None:
        data["pitch"] = max(-40, min(40, args.pitch))
    if args.roll is not None:
        data["roll"] = max(-40, min(40, args.roll))
    if args.yaw is not None:
        data["yaw"] = max(-180, min(180, args.yaw))
    
    result = api_post("/api/move_head", data)
    print(json.dumps(result, indent=2))


def cmd_antennas(args):
    """Move antennas."""
    data = {
        "left": args.left,
        "right": args.right,
        "duration": args.duration
    }
    result = api_post("/api/move_antennas", data)
    print(json.dumps(result, indent=2))


def cmd_capture(args):
    """Capture camera image."""
    result = api_get("/api/hardware/camera_check")
    
    if "image" in result:
        # Decode base64 and save
        img_data = base64.b64decode(result["image"])
        output = args.output or "reachy_capture.jpg"
        with open(output, "wb") as f:
            f.write(img_data)
        print(f"Saved to {output}")
    elif "frame" in result:
        img_data = base64.b64decode(result["frame"])
        output = args.output or "reachy_capture.jpg"
        with open(output, "wb") as f:
            f.write(img_data)
        print(f"Saved to {output}")
    else:
        print(json.dumps(result, indent=2))


def cmd_say(args):
    """Text-to-speech (placeholder - implement with Chatterbox)."""
    text = " ".join(args.text)
    # For now, just print - will integrate Chatterbox later
    print(f"[TTS] Would say: {text}")
    print("Note: Chatterbox TTS integration pending")


def cmd_record_start(args):
    """Start audio recording."""
    result = api_post("/api/audio/start_recording")
    print(json.dumps(result, indent=2))


def cmd_record_stop(args):
    """Stop audio recording."""
    result = api_post("/api/audio/stop_recording")
    print(json.dumps(result, indent=2))


def cmd_recordings(args):
    """List recordings."""
    result = api_get("/api/audio/list")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Reachy Mini control")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status commands
    subparsers.add_parser("status", help="Get robot status")
    subparsers.add_parser("state", help="Get daemon state")

    # Wake/sleep
    subparsers.add_parser("wake", help="Wake up robot")
    subparsers.add_parser("sleep", help="Put robot to sleep")
    subparsers.add_parser("zero", help="Move to neutral position")

    # Head
    head_parser = subparsers.add_parser("head", help="Move head")
    head_parser.add_argument("--pitch", type=float, help="Pitch (-40 to 40)")
    head_parser.add_argument("--roll", type=float, help="Roll (-40 to 40)")
    head_parser.add_argument("--yaw", type=float, help="Yaw (-180 to 180)")
    head_parser.add_argument("--duration", type=float, default=1.0, help="Duration (s)")

    # Antennas
    ant_parser = subparsers.add_parser("antennas", help="Move antennas")
    ant_parser.add_argument("--left", type=float, default=0, help="Left antenna angle")
    ant_parser.add_argument("--right", type=float, default=0, help="Right antenna angle")
    ant_parser.add_argument("--duration", type=float, default=0.5, help="Duration (s)")

    # Camera
    cap_parser = subparsers.add_parser("capture", help="Capture image")
    cap_parser.add_argument("--output", "-o", help="Output filename")

    # TTS
    say_parser = subparsers.add_parser("say", help="Text-to-speech")
    say_parser.add_argument("text", nargs="+", help="Text to speak")

    # Audio recording
    subparsers.add_parser("record-start", help="Start recording")
    subparsers.add_parser("record-stop", help="Stop recording")
    subparsers.add_parser("recordings", help="List recordings")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "state": cmd_state,
        "wake": cmd_wake,
        "sleep": cmd_sleep,
        "zero": cmd_zero,
        "head": cmd_head,
        "antennas": cmd_antennas,
        "capture": cmd_capture,
        "say": cmd_say,
        "record-start": cmd_record_start,
        "record-stop": cmd_record_stop,
        "recordings": cmd_recordings,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
