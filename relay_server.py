#!/usr/bin/env python3
"""Relay robot messages to Telegram via Bot API directly.

This server receives POSTs from the robot's talk_wireless.py and forwards
messages to Telegram using the Bot API (not OpenClaw, to avoid double messages).

Usage:
    python relay_server.py

Environment:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_CHAT_ID: Chat ID to send to (required)
    RELAY_PORT: Server port (default: 18800)
"""
import os
import httpx
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Reachy Telegram Relay")

# Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
RELAY_PORT = int(os.getenv("RELAY_PORT", "18800"))


class Message(BaseModel):
    role: str  # "user" or "reachy"
    text: str


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "chat_id": TELEGRAM_CHAT_ID, "has_token": bool(TELEGRAM_BOT_TOKEN)}


@app.post("/telegram")
async def post_telegram(msg: Message):
    """Forward message to Telegram via Bot API directly."""
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "No TELEGRAM_BOT_TOKEN set"}

    # Format message with emoji prefix
    if msg.role == "user":
        prefix = "🎤 You:"
    elif msg.role == "reachy":
        prefix = "🤖 Reachy:"
    elif msg.role == "system":
        prefix = "⚙️"
    else:
        prefix = f"{msg.role}:"

    full_text = f"{prefix} {msg.text}" if prefix else msg.text

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": full_text,
                    "parse_mode": "Markdown",
                    "disable_notification": True,
                },
                timeout=10.0,
            )
            result = response.json()
            if not result.get("ok"):
                # Retry without markdown if parsing fails
                response = await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": full_text,
                        "disable_notification": True,
                    },
                    timeout=10.0,
                )
                result = response.json()
            return {"ok": result.get("ok", False), "sent": full_text}

    except Exception as e:
        return {"ok": False, "error": str(e)}


class SpotifyQuery(BaseModel):
    query: str
    type: str = "track"


class SpotifyAction(BaseModel):
    action: str
    value: int | None = None


async def _run_spotify(*args: str) -> str:
    """Run spotify_player CLI on Mac."""
    cmd = ["/opt/homebrew/bin/spotify_player", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode().strip()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            return f"Error: {err or output}"
        return output
    except Exception as e:
        return f"Error: {e}"


@app.post("/spotify/play")
async def spotify_play(req: SpotifyQuery):
    """Search and play on Spotify."""
    output = await _run_spotify("playback", "start", "--name", req.query, "--type", req.type)
    if output.startswith("Error"):
        return {"error": output}
    return {"status": "playing", "query": req.query, "type": req.type}


@app.post("/spotify/control")
async def spotify_control(req: SpotifyAction):
    """Control Spotify playback."""
    if req.action == "next":
        output = await _run_spotify("playback", "next")
    elif req.action == "previous":
        output = await _run_spotify("playback", "previous")
    elif req.action == "play":
        output = await _run_spotify("playback", "play-pause")
    elif req.action == "pause":
        output = await _run_spotify("playback", "play-pause")
    elif req.action == "shuffle":
        output = await _run_spotify("playback", "shuffle")
    elif req.action == "volume" and req.value is not None:
        output = await _run_spotify("playback", "volume", str(req.value))
    else:
        return {"error": f"Unknown action: {req.action}"}
    if output.startswith("Error"):
        return {"error": output}
    return {"status": "ok", "action": req.action}


@app.get("/spotify/status")
async def spotify_status():
    """Get current playback."""
    output = await _run_spotify("playback")
    if output.startswith("Error"):
        return {"error": output}
    return {"status": "ok", "now_playing": output}


def main():
    print("=" * 50)
    print("Reachy Telegram Relay Server (Direct Bot API)")
    print("=" * 50)
    print(f"Telegram chat: {TELEGRAM_CHAT_ID}")
    print(f"Bot token: {'set' if TELEGRAM_BOT_TOKEN else 'MISSING!'}")
    print(f"Listening on: http://0.0.0.0:{RELAY_PORT}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=RELAY_PORT)


if __name__ == "__main__":
    main()
