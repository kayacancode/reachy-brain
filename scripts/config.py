#!/usr/bin/env python3
"""
Configuration loader for Reachy Brain.
Reads from ~/.config/reachy-brain/config.json or environment variables.
"""

import os
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "reachy": {
        "ip": "192.168.1.171",
        "port": 8042,
        "ssh_user": "pollen",
        "ssh_pass": "root"
    },
    "honcho": {
        "api_key": "",
        "workspace": "reachy-brain"
    },
    "agent": {
        "name": "ReachyBot",
        "personality": "A friendly robot assistant"
    },
    "stt": {
        "provider": "faster-whisper",  # or "whisper" for original
        "model": "base",
        "device": "cpu",
        "compute_type": "int8"
    },
    "tts": {
        "provider": "piper",  # piper, chatterbox, macos
        "piper_voice": "en_US-lessac-medium",
        "cache_enabled": True,
        "cache_dir": "~/.cache/reachy-tts",
        "fallback_to_macos": True,
        "fallback_to_chatterbox": False,
        "chatterbox_space": "ResembleAI/chatterbox-turbo-demo"
    },
    "wake_word": {
        "enabled": True,
        "bot_name": "OpenClaw",
        "model_path": "~/.config/reachy-brain/wake_words/{bot_name}.onnx",
        "threshold": 0.5,
        "confirmation_sound": True,
        "antenna_response": True
    },
    "clawdbot": {
        "host": "localhost",
        "port": 18789,
        "token": ""
    }
}


def load_config() -> dict:
    """Load configuration from file or environment."""
    config = DEFAULT_CONFIG.copy()
    
    # Try loading from file
    config_path = os.environ.get("REACHY_CONFIG", 
        Path.home() / ".config" / "reachy-brain" / "config.json")
    
    if Path(config_path).exists():
        try:
            with open(config_path) as f:
                file_config = json.load(f)
            config = _deep_merge(config, file_config)
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
    
    # Override with environment variables
    env_overrides = {
        "REACHY_IP": ("reachy", "ip"),
        "REACHY_PORT": ("reachy", "port"),
        "REACHY_SSH_USER": ("reachy", "ssh_user"),
        "REACHY_SSH_PASS": ("reachy", "ssh_pass"),
        "HONCHO_API_KEY": ("honcho", "api_key"),
        "HONCHO_WORKSPACE": ("honcho", "workspace"),
        "CLAWDBOT_HOST": ("clawdbot", "host"),
        "CLAWDBOT_PORT": ("clawdbot", "port"),
        "CLAWDBOT_TOKEN": ("clawdbot", "token"),
        # STT
        "STT_PROVIDER": ("stt", "provider"),
        "WHISPER_MODEL": ("stt", "model"),
        "WHISPER_DEVICE": ("stt", "device"),
        "WHISPER_COMPUTE_TYPE": ("stt", "compute_type"),
        # TTS
        "TTS_PROVIDER": ("tts", "provider"),
        "PIPER_VOICE": ("tts", "piper_voice"),
        "TTS_CACHE_ENABLED": ("tts", "cache_enabled"),
        # Wake word
        "WAKE_WORD_ENABLED": ("wake_word", "enabled"),
        "WAKE_WORD_BOT_NAME": ("wake_word", "bot_name"),
        "WAKE_WORD_THRESHOLD": ("wake_word", "threshold"),
        "WAKE_WORD_CONFIRMATION_SOUND": ("wake_word", "confirmation_sound"),
        "WAKE_WORD_ANTENNA_RESPONSE": ("wake_word", "antenna_response"),
    }
    
    for env_var, path in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            section, key = path
            if section not in config:
                config[section] = {}
            config[section][key] = value
    
    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# Singleton config instance
_config = None

def get_config() -> dict:
    """Get the configuration (loads once, caches)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


# Convenience accessors
def reachy_url() -> str:
    cfg = get_config()
    return f"http://{cfg['reachy']['ip']}:{cfg['reachy']['port']}"

def reachy_ssh() -> tuple:
    cfg = get_config()
    return (cfg['reachy']['ssh_user'], cfg['reachy']['ssh_pass'], cfg['reachy']['ip'])

def honcho_key() -> str:
    return get_config()['honcho']['api_key']

def honcho_workspace() -> str:
    return get_config()['honcho']['workspace']

def clawdbot_url() -> str:
    cfg = get_config()
    return f"http://{cfg['clawdbot']['host']}:{cfg['clawdbot']['port']}"

def clawdbot_token() -> str:
    return get_config()['clawdbot']['token']

def stt_provider() -> str:
    return get_config()['stt']['provider']

def stt_model() -> str:
    return get_config()['stt']['model']

def tts_provider() -> str:
    return get_config()['tts']['provider']

def tts_cache_enabled() -> bool:
    return get_config()['tts']['cache_enabled']

def wake_word_enabled() -> bool:
    return get_config()['wake_word']['enabled']

def wake_word_bot_name() -> str:
    return get_config()['wake_word']['bot_name']

def wake_word_threshold() -> float:
    return float(get_config()['wake_word']['threshold'])


if __name__ == "__main__":
    import json
    print(json.dumps(load_config(), indent=2))
