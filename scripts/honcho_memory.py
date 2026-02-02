#!/usr/bin/env python3
"""
Honcho memory integration for KayaCan + Reachy Mini.
Uses v3 SDK.
"""

import os
from honcho import Honcho

HONCHO_API_KEY = os.environ.get("HONCHO_API_KEY", 
    "hch-v2-dext6ss128iv3yjoeyy1lfzsnnm7vsx3g9f302c2wqfhq5ahx5icl74ucjf74mg3")
WORKSPACE = "forever22"


def get_client():
    return Honcho(api_key=HONCHO_API_KEY, workspace_id=WORKSPACE)


def get_context(query: str) -> str:
    """Query Honcho for context about Kaya."""
    client = get_client()
    kaya = client.peer("kaya")
    return kaya.chat(query) or ""


def save_messages(user_text: str, assistant_text: str, session_name: str = "reachy-voice"):
    """Save a conversation exchange to Honcho."""
    client = get_client()
    kaya = client.peer("kaya")
    kayacan = client.peer("kayacan")
    session = client.session(session_name)
    session.add_messages([
        kaya.message(user_text),
        kayacan.message(assistant_text)
    ])


def test():
    print("🧠 Testing Honcho connection...")
    client = get_client()
    kaya = client.peer("kaya")
    
    # Save test
    kayacan = client.peer("kayacan")
    session = client.session("test-session")
    session.add_messages([
        kaya.message("Kaya loves building AI tools and robots."),
        kayacan.message("Got it! I'll remember that about you.")
    ])
    print("✅ Messages saved!")
    
    # Query
    response = kaya.chat("What do you know about this person?")
    print(f"🧠 Honcho: {response}")


if __name__ == "__main__":
    test()
