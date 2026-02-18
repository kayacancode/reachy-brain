"""Robot control tools for direct talk mode.

Simplified tool definitions that use HTTP API to control the robot.
Includes Spotify playback control via spotify_player CLI.
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Available dances from the Pollen library
AVAILABLE_DANCES = [
    "simple_nod",
    "head_tilt_roll",
    "side_to_side_sway",
    "dizzy_spin",
    "stumble_and_recover",
    "interwoven_spirals",
    "sharp_side_tilt",
    "side_peekaboo",
    "yeah_nod",
    "uh_huh_tilt",
    "neck_recoil",
    "chin_lead",
    "groovy_sway_and_roll",
    "chicken_peck",
    "side_glance_flick",
    "polyrhythm_combo",
    "grid_snap",
    "pendulum_swing",
    "jackson_square",
]

# Available emotions from the Pollen library
AVAILABLE_EMOTIONS = [
    "happy",
    "sad",
    "surprised",
    "angry",
    "confused",
    "thinking",
    "curious",
    "sleepy",
    "excited",
]

# Available custom animations from the bridge
AVAILABLE_ANIMATIONS = [
    "look",
    "nod",
    "wiggle",
    "think",
    "surprise",
    "happy",
    "wave",
    "listen",
    "alert",
    "sad",
    "reset",
]

# Tool definitions for Claude (OpenAI-compatible format)
# Keep descriptions short to avoid OpenClaw timeout
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "dance",
            "description": "Play a dance move when asked to dance or celebrate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "move": {
                        "type": "string",
                        "description": "Dance name or 'random'",
                    }
                },
                "required": ["move"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emotion",
            "description": "Express an emotion physically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "emotion": {
                        "type": "string",
                        "description": "happy, sad, surprised, angry, confused, curious",
                    }
                },
                "required": ["emotion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "animate",
            "description": "Quick animation: nod, wave, think, look, wiggle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "animation": {
                        "type": "string",
                        "description": "Animation name",
                    }
                },
                "required": ["animation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_head",
            "description": "Move head position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pitch": {"type": "number", "description": "Up/down (-40 to 40)"},
                    "yaw": {"type": "number", "description": "Left/right (-180 to 180)"},
                    "roll": {"type": "number", "description": "Tilt (-40 to 40)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_at",
            "description": "Look in a direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right", "center"],
                    }
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "camera",
            "description": "Take a picture to see surroundings.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search memory about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What to remember"}
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Save a fact about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "Fact to save"}
                },
                "required": ["fact"],
            },
        },
    },
]


# Spotify tool definitions
SPOTIFY_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "spotify_play",
            "description": "Play a song, artist, album, or playlist on Spotify. Use when user asks to play music.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Song name, artist, album, or playlist to play"},
                    "type": {"type": "string", "enum": ["track", "artist", "album", "playlist"], "description": "What to search for (default: track)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_control",
            "description": "Control Spotify playback: skip, previous, pause, resume, shuffle, volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["next", "previous", "play", "pause", "shuffle", "volume"],
                        "description": "Playback action",
                    },
                    "value": {"type": "integer", "description": "Volume level 0-100 (only for volume action)"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_status",
            "description": "Get current Spotify playback status (what's playing now).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


class ToolExecutor:
    """Executes robot control tools via HTTP API."""

    def __init__(
        self,
        robot_ip: str,
        bridge_port: int = 9000,
        daemon_port: int = 8000,
        memory=None,
        vision=None,
        user_id: str = "anonymous",
    ):
        """Initialize tool executor.

        Args:
            robot_ip: IP address of the robot.
            bridge_port: Port for the bridge server (audio, animations).
            daemon_port: Port for the robot daemon (dances, emotions).
            memory: ConversationMemory instance for recall/remember.
            vision: VisionSystem instance for camera.
            user_id: Current user ID for memory operations.
        """
        self.robot_ip = robot_ip
        self.bridge_url = f"http://{robot_ip}:{bridge_port}"
        self.daemon_url = f"http://{robot_ip}:{daemon_port}"
        self.memory = memory
        self.vision = vision
        self.user_id = user_id
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    def set_user_id(self, user_id: str):
        """Update the current user ID."""
        self.user_id = user_id

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool and return the result."""
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        try:
            if tool_name == "dance":
                return await self._dance(arguments.get("move", "random"))
            elif tool_name == "emotion":
                return await self._emotion(arguments.get("emotion", "happy"))
            elif tool_name == "animate":
                return await self._animate(arguments.get("animation", "nod"))
            elif tool_name == "move_head":
                return await self._move_head(
                    pitch=arguments.get("pitch", 0),
                    yaw=arguments.get("yaw", 0),
                    roll=arguments.get("roll", 0),
                    duration=arguments.get("duration", 1.0),
                )
            elif tool_name == "look_at":
                return await self._look_at(arguments.get("direction", "forward"))
            elif tool_name == "camera":
                return await self._camera()
            elif tool_name == "recall":
                return await self._recall(arguments.get("question", ""))
            elif tool_name == "remember":
                return await self._remember(arguments.get("fact", ""))
            elif tool_name == "spotify_play":
                return await self._spotify_play(
                    arguments.get("query", ""),
                    arguments.get("type", "track"),
                )
            elif tool_name == "spotify_control":
                return await self._spotify_control(
                    arguments.get("action", "next"),
                    arguments.get("value"),
                )
            elif tool_name == "spotify_status":
                return await self._spotify_status()
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}

    async def _dance(self, move: str) -> dict:
        """Play a dance move."""
        if move == "random":
            import random
            move = random.choice(AVAILABLE_DANCES)

        url = f"{self.daemon_url}/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/{move}"
        try:
            response = await self._client.post(url)
            if response.status_code == 200:
                return {"status": "dancing", "move": move}
            return {"error": f"Dance failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Dance request failed: {e}"}

    async def _emotion(self, emotion: str) -> dict:
        """Play an emotion."""
        url = f"{self.daemon_url}/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{emotion}"
        try:
            response = await self._client.post(url)
            if response.status_code == 200:
                return {"status": "expressing", "emotion": emotion}
            return {"error": f"Emotion failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Emotion request failed: {e}"}

    async def _animate(self, animation: str) -> dict:
        """Play a custom animation via bridge."""
        url = f"{self.bridge_url}/animate/{animation}"
        try:
            response = await self._client.post(url)
            if response.status_code == 200:
                return {"status": "animating", "animation": animation}
            return {"error": f"Animation failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Animation request failed: {e}"}

    async def _move_head(self, pitch: float, yaw: float, roll: float, duration: float) -> dict:
        """Move head to position."""
        url = f"{self.daemon_url}/api/move/goto"
        payload = {
            "head_pose": {
                "x": 0,
                "y": 0,
                "z": 0.01,
                "roll": roll * 0.0174533,  # Convert degrees to radians
                "pitch": pitch * 0.0174533,
                "yaw": yaw * 0.0174533,
            },
            "duration": duration,
        }
        try:
            response = await self._client.post(url, json=payload)
            if response.status_code == 200:
                return {"status": "moved", "pitch": pitch, "yaw": yaw, "roll": roll}
            return {"error": f"Move failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Move request failed: {e}"}

    async def _look_at(self, direction: str) -> dict:
        """Look in a direction."""
        directions = {
            "up": (20, 0, 0),
            "down": (-15, 0, 0),
            "left": (0, 30, 0),
            "right": (0, -30, 0),
            "center": (0, 0, 0),
            "forward": (0, 0, 0),
        }
        pitch, yaw, roll = directions.get(direction, (0, 0, 0))
        return await self._move_head(pitch, yaw, roll, 0.5)

    async def _camera(self) -> dict:
        """Take a picture and return description."""
        if self.vision:
            jpeg_bytes = await self.vision.capture_frame_jpeg()
            if jpeg_bytes:
                # Return base64 encoded image for Claude to analyze
                b64_image = base64.b64encode(jpeg_bytes).decode('utf-8')
                return {
                    "status": "captured",
                    "image_base64": b64_image,
                    "description": "Image captured. Analyze what you see.",
                }

        # Fallback to HTTP snapshot
        url = f"{self.bridge_url}/snapshot"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                b64_image = base64.b64encode(response.content).decode('utf-8')
                return {
                    "status": "captured",
                    "image_base64": b64_image,
                    "description": "Image captured. Analyze what you see.",
                }
            return {"error": f"Camera failed: {response.status_code}"}
        except Exception as e:
            return {"error": f"Camera request failed: {e}"}

    async def _spotify_play(self, query: str, search_type: str = "track") -> dict:
        """Search and play something on Spotify via Mac relay."""
        try:
            relay_url = os.getenv("TELEGRAM_RELAY", "").replace("/telegram", "")
            if not relay_url:
                relay_url = f"http://{os.getenv('MAC_IP', '10.4.33.158')}:18801"
            response = await self._client.post(
                f"{relay_url}/spotify/play",
                json={"query": query, "type": search_type},
            )
            return response.json()
        except Exception as e:
            return {"error": f"Spotify play failed: {e}"}

    async def _spotify_control(self, action: str, value: int = None) -> dict:
        """Control Spotify playback via Mac relay."""
        try:
            relay_url = os.getenv("TELEGRAM_RELAY", "").replace("/telegram", "")
            if not relay_url:
                relay_url = f"http://{os.getenv('MAC_IP', '10.4.33.158')}:18801"
            payload = {"action": action}
            if value is not None:
                payload["value"] = value
            response = await self._client.post(
                f"{relay_url}/spotify/control",
                json=payload,
            )
            return response.json()
        except Exception as e:
            return {"error": f"Spotify control failed: {e}"}

    async def _spotify_status(self) -> dict:
        """Get current playback status via Mac relay."""
        try:
            relay_url = os.getenv("TELEGRAM_RELAY", "").replace("/telegram", "")
            if not relay_url:
                relay_url = f"http://{os.getenv('MAC_IP', '10.4.33.158')}:18801"
            response = await self._client.get(f"{relay_url}/spotify/status")
            return response.json()
        except Exception as e:
            return {"error": f"Spotify status failed: {e}"}

    async def _recall(self, question: str) -> dict:
        """Recall information from memory."""
        if not self.memory:
            return {"memory": "I don't have access to my memory right now."}

        result = await self.memory.chat_about_user(self.user_id, question)
        return {"memory": result}

    async def _remember(self, fact: str) -> dict:
        """Save a fact to memory."""
        if not self.memory:
            return {"saved": False, "error": "Memory not available"}

        success = await self.memory.create_conclusion(self.user_id, fact)
        if success:
            return {"saved": True, "fact": fact}
        return {"saved": False, "error": "Failed to save to memory"}


def get_tool_definitions() -> list[dict]:
    """Return the tool definitions for Claude."""
    return TOOL_DEFINITIONS + SPOTIFY_TOOL_DEFINITIONS


def parse_tool_calls(response: dict) -> list[tuple[str, dict]]:
    """Parse tool calls from a Claude/OpenAI response.

    Returns list of (tool_name, arguments) tuples.
    """
    tool_calls = []

    # Check for OpenAI format
    choices = response.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        calls = message.get("tool_calls", [])
        for call in calls:
            if call.get("type") == "function":
                func = call.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append((name, args))

    return tool_calls


def has_tool_calls(response: dict) -> bool:
    """Check if a response contains tool calls."""
    choices = response.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        return bool(message.get("tool_calls"))
    return False


def get_response_text(response: dict) -> str | None:
    """Extract text content from a response."""
    choices = response.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        return message.get("content")
    return None
