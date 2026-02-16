#!/usr/bin/env python3
"""Relay robot messages to Telegram via Bot API directly.

This server receives POSTs from the robot's talk_wireless.py and forwards
messages to Telegram using the Bot API (not OpenClaw, to avoid double messages).

Usage:
    python relay_server.py

Environment:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_CHAT_ID: Chat ID to send to (default: REDACTED_CHAT_ID)
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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "REDACTED_CHAT_ID")
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
