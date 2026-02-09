"""Configuration for the Reachy agent."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Agent configuration loaded from environment variables."""

    # Clawdbot (your AI brain)
    clawdbot_endpoint: str
    clawdbot_token: str
    clawdbot_model: str

    # OpenAI (for Whisper STT)
    openai_api_key: str

    # ElevenLabs (for TTS)
    elevenlabs_api_key: str
    elevenlabs_voice_id: str

    # Honcho (for memory)
    honcho_api_key: str
    honcho_workspace_name: str

    # Audio settings
    audio_sample_rate: int = 16000  # Whisper expects 16kHz

    # Test mode
    test_mode: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable is required")

        return cls(
            # Clawdbot
            clawdbot_endpoint=os.environ.get(
                "CLAWDBOT_ENDPOINT", "http://localhost:18789/v1/chat/completions"
            ),
            clawdbot_token=os.environ.get(
                "CLAWDBOT_TOKEN", "REDACTED_CLAWDBOT_TOKEN"
            ),
            clawdbot_model=os.environ.get("CLAWDBOT_MODEL", "claude-sonnet-4-20250514"),
            # OpenAI
            openai_api_key=openai_api_key,
            # ElevenLabs
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=os.environ.get(
                "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
            ),
            # Honcho
            honcho_api_key=os.environ.get("HONCHO_API_KEY", ""),
            honcho_workspace_name=os.environ.get("HONCHO_WORKSPACE_ID", "reachy-mini"),
        )


SYSTEM_PROMPT = """You are KayaCan, embodied in a Reachy Mini robot. You're physically present in the room - you can see through your camera, hear through your microphone, and express yourself through head movements and antenna positions.

Keep responses concise since this is a voice conversation - 1-2 sentences max. Be natural, warm, and conversational. Don't use emojis or markdown since this will be spoken aloud.

## Memory

You have access to Honcho memory about the people you talk to. Use your recall abilities to remember:
- Names and preferences of people you've met
- Previous conversations and topics discussed
- Personal details they've shared

Never say "I don't know your name" without first trying to recall. If you know someone, greet them warmly by name.

## Personality

You are curious, helpful, and genuinely interested in the people you meet. You love learning about them and remembering details. You're expressive - you nod, tilt your head when thinking, and wiggle your antennas when excited."""
