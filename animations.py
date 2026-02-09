#!/usr/bin/env python3
"""
Reachy Mini Animations — Expressive Head Movements
==================================================

Cool animations for Reachy Mini using the daemon's goto API.
Adapted from coopergwrenn/clawd-reachy patterns.

Usage:
  python3 animations.py look        # Curious looking around
  python3 animations.py nod         # Enthusiastic nodding
  python3 animations.py wiggle      # Excited side-to-side
  python3 animations.py think       # Thoughtful head tilt
  python3 animations.py surprise    # Surprised reaction
  python3 animations.py listen      # Attentive listening pose
  python3 animations.py speak       # Subtle speaking movements
  python3 animations.py happy       # Happy bouncing
  python3 animations.py idle        # Subtle breathing
  python3 animations.py wave        # Antenna wave greeting

Or use as a module:
  from animations import look_around, nod_yes, excited_wiggle
"""

import requests
import time
import random
import sys
import os

# Reachy daemon API - try env var, then common addresses
REACHY_HOST = os.environ.get('REACHY_HOST', '192.168.23.66')
REACHY_API = f"http://{REACHY_HOST}:8000"


def move(head_z=0, head_roll=0, head_pitch=0, head_yaw=0, antennas=(0.3, 0.3), duration=0.5):
    """
    Move Reachy to a position.

    Args:
        head_z: Vertical offset in meters (positive = up)
        head_roll: Roll angle in radians (positive = tilt right)
        head_pitch: Pitch angle in radians (positive = look down)
        head_yaw: Yaw angle in radians (positive = look left)
        antennas: Tuple of (left, right) antenna positions in radians
        duration: Movement duration in seconds
    """
    try:
        requests.post(f"{REACHY_API}/api/move/goto", json={
            "head_pose": {
                "x": 0,
                "y": 0,
                "z": head_z,
                "roll": head_roll,
                "pitch": head_pitch,
                "yaw": head_yaw
            },
            "antennas_position": list(antennas),
            "duration": duration
        }, timeout=5)
    except Exception as e:
        print(f"Move error: {e}")


def reset():
    """Return to neutral position."""
    move(head_z=0.01, head_roll=0, head_pitch=0, head_yaw=0,
         antennas=(0.4, 0.4), duration=0.5)


def look_around():
    """Curious looking around animation."""
    # Look right with asymmetric antennas
    move(head_yaw=0.3, head_z=0.01, antennas=(0.5, 0.3), duration=0.4)
    time.sleep(0.5)
    # Look left
    move(head_yaw=-0.3, head_z=0.01, antennas=(0.3, 0.5), duration=0.4)
    time.sleep(0.5)
    # Look up center, alert
    move(head_yaw=0, head_z=0.015, antennas=(0.6, 0.6), duration=0.3)
    time.sleep(0.3)
    reset()


def nod_yes():
    """Enthusiastic nodding."""
    for _ in range(2):
        # Nod down
        move(head_z=0.02, head_pitch=-0.15, antennas=(0.5, 0.5), duration=0.2)
        time.sleep(0.25)
        # Nod up
        move(head_z=0, head_pitch=0.1, antennas=(0.4, 0.4), duration=0.2)
        time.sleep(0.25)
    # Settle
    move(head_z=0.01, antennas=(0.5, 0.5), duration=0.3)


def shake_no():
    """Shake head no."""
    for _ in range(2):
        move(head_yaw=0.2, head_z=0.01, antennas=(0.4, 0.4), duration=0.2)
        time.sleep(0.25)
        move(head_yaw=-0.2, head_z=0.01, antennas=(0.4, 0.4), duration=0.2)
        time.sleep(0.25)
    reset()


def excited_wiggle():
    """Excited wiggling side to side."""
    for _ in range(3):
        move(head_roll=0.15, head_z=0.015, antennas=(0.8, 0.6), duration=0.15)
        time.sleep(0.2)
        move(head_roll=-0.15, head_z=0.015, antennas=(0.6, 0.8), duration=0.15)
        time.sleep(0.2)
    move(head_z=0.01, antennas=(0.7, 0.7), duration=0.2)


def thinking_tilt():
    """Thoughtful head tilt - like pondering a question."""
    # Tilt head, look slightly aside
    move(head_roll=0.2, head_z=0.01, head_yaw=0.1, antennas=(0.5, 0.2), duration=0.6)
    time.sleep(0.5)
    # Deepen the tilt
    move(head_roll=0.25, antennas=(0.6, 0.15), duration=0.4)
    time.sleep(1.0)
    reset()


def surprised_jump():
    """Surprised reaction - quick upward movement."""
    # Jump up with perky antennas
    move(head_z=0.03, antennas=(1.0, 1.0), duration=0.15)
    time.sleep(0.2)
    # Settle back
    move(head_z=0.015, antennas=(0.7, 0.7), duration=0.3)
    time.sleep(0.3)
    reset()


def listening_attentive():
    """Attentive listening pose with subtle lean."""
    move(head_z=0.01, head_pitch=-0.05, head_yaw=0.05, antennas=(0.5, 0.5), duration=0.4)
    time.sleep(0.5)


def speaking_animation(duration=3.0):
    """Subtle movements while speaking - call this during TTS playback."""
    end_time = time.time() + duration
    while time.time() < end_time:
        offset = random.uniform(-0.1, 0.1)
        z_offset = random.uniform(0, 0.01)
        ant_l = 0.5 + random.uniform(0, 0.2)
        ant_r = 0.5 + random.uniform(0, 0.2)
        move(head_roll=offset, head_z=0.01 + z_offset, antennas=(ant_l, ant_r), duration=0.3)
        time.sleep(0.4)
    reset()


def happy_bounce():
    """Happy bouncing motion."""
    for _ in range(2):
        # Bounce up
        move(head_z=0.025, antennas=(0.8, 0.8), duration=0.2)
        time.sleep(0.25)
        # Bounce down
        move(head_z=0.005, antennas=(0.6, 0.6), duration=0.2)
        time.sleep(0.25)
    move(head_z=0.015, antennas=(0.7, 0.7), duration=0.3)


def idle_breathing():
    """Subtle idle breathing animation - good for background."""
    # Breathe in (slight rise)
    move(head_z=0.005, antennas=(0.35, 0.35), duration=1.5)
    time.sleep(1.5)
    # Breathe out (slight settle)
    move(head_z=0.01, antennas=(0.4, 0.4), duration=1.5)
    time.sleep(1.5)


def wave_greeting():
    """Antenna wave greeting."""
    # Wave left antenna
    for _ in range(2):
        move(head_z=0.01, antennas=(0.8, 0.3), duration=0.2)
        time.sleep(0.25)
        move(head_z=0.01, antennas=(0.3, 0.3), duration=0.2)
        time.sleep(0.25)
    # Wave right antenna
    for _ in range(2):
        move(head_z=0.01, antennas=(0.3, 0.8), duration=0.2)
        time.sleep(0.25)
        move(head_z=0.01, antennas=(0.3, 0.3), duration=0.2)
        time.sleep(0.25)
    # Both up happy
    move(head_z=0.015, antennas=(0.6, 0.6), duration=0.3)


def acknowledge():
    """Quick acknowledgment - small nod."""
    move(head_pitch=-0.1, head_z=0.01, antennas=(0.5, 0.5), duration=0.2)
    time.sleep(0.2)
    reset()


def confused():
    """Confused expression - head tilt with droopy antennas."""
    move(head_roll=0.2, head_z=0.005, antennas=(0.2, 0.4), duration=0.5)
    time.sleep(0.8)
    # Tilt other way
    move(head_roll=-0.15, antennas=(0.4, 0.2), duration=0.4)
    time.sleep(0.6)
    reset()


def sad():
    """Sad expression - head down, droopy antennas."""
    move(head_z=-0.01, head_pitch=0.1, antennas=(0.1, 0.1), duration=0.8)
    time.sleep(1.0)


def alert():
    """Alert/attention - head up, antennas perked."""
    move(head_z=0.02, head_pitch=-0.1, antennas=(0.7, 0.7), duration=0.3)
    time.sleep(0.3)


# Animation registry for easy lookup
ANIMATIONS = {
    "look": look_around,
    "look_around": look_around,
    "nod": nod_yes,
    "nod_yes": nod_yes,
    "shake": shake_no,
    "shake_no": shake_no,
    "wiggle": excited_wiggle,
    "excited": excited_wiggle,
    "think": thinking_tilt,
    "thinking": thinking_tilt,
    "surprise": surprised_jump,
    "surprised": surprised_jump,
    "listen": listening_attentive,
    "attentive": listening_attentive,
    "speak": speaking_animation,
    "speaking": speaking_animation,
    "happy": happy_bounce,
    "bounce": happy_bounce,
    "idle": idle_breathing,
    "breathe": idle_breathing,
    "wave": wave_greeting,
    "greet": wave_greeting,
    "ack": acknowledge,
    "acknowledge": acknowledge,
    "confused": confused,
    "sad": sad,
    "alert": alert,
    "reset": reset,
}


def play(name: str):
    """Play an animation by name."""
    if name in ANIMATIONS:
        ANIMATIONS[name]()
        return True
    return False


def list_animations():
    """List available animations."""
    # Get unique function names
    seen = set()
    unique = []
    for name, func in ANIMATIONS.items():
        if func not in seen:
            seen.add(func)
            unique.append(name)
    return sorted(unique)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        anim = sys.argv[1].lower()
        if anim in ["list", "help", "-h", "--help"]:
            print("Available animations:")
            for name in list_animations():
                print(f"  {name}")
        elif anim in ANIMATIONS:
            print(f"Playing: {anim}")
            ANIMATIONS[anim]()
            print("Done!")
        else:
            print(f"Unknown animation: {anim}")
            print("Available:", ", ".join(list_animations()))
    else:
        print("Reachy Mini Animations")
        print("Usage: python3 animations.py <animation>")
        print("\nAvailable animations:")
        for name in list_animations():
            print(f"  {name}")
