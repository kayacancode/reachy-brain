#!/usr/bin/env python3
"""Simple audio playback server for Reachy Mini.

Plays WAV files via HTTP without importing the Reachy SDK.
Tries multiple playback methods: GStreamer, paplay, aplay.

Run on the robot:
    python3 audio_server.py
"""

import asyncio
import logging
import subprocess
import tempfile
import os
import shutil
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PORT = 9000

# Find available audio player at startup
AUDIO_PLAYER = None
AUDIO_ARGS = []

def find_audio_player():
    """Find an available audio player."""
    global AUDIO_PLAYER, AUDIO_ARGS

    # On Reachy Mini, use aplay with shared dmix device first
    # This allows mixing with the daemon's audio
    if shutil.which('aplay') and os.path.exists(os.path.expanduser('~/.asoundrc')):
        AUDIO_PLAYER = 'aplay'
        AUDIO_ARGS = ['-D', 'reachymini_audio_sink']
        logger.info("Using aplay with reachymini_audio_sink (shared device)")
        return

    # Try paplay (PulseAudio)
    if shutil.which('paplay'):
        AUDIO_PLAYER = 'paplay'
        AUDIO_ARGS = []
        logger.info("Using paplay for audio")
        return

    # Try GStreamer
    if shutil.which('gst-play-1.0'):
        AUDIO_PLAYER = 'gst-play-1.0'
        AUDIO_ARGS = ['--no-interactive']
        logger.info("Using gst-play-1.0 for audio")
        return

    # Try mpv (minimal player)
    if shutil.which('mpv'):
        AUDIO_PLAYER = 'mpv'
        AUDIO_ARGS = ['--no-video', '--really-quiet']
        logger.info("Using mpv for audio")
        return

    # Try ffplay
    if shutil.which('ffplay'):
        AUDIO_PLAYER = 'ffplay'
        AUDIO_ARGS = ['-nodisp', '-autoexit', '-loglevel', 'quiet']
        logger.info("Using ffplay for audio")
        return

    # Fallback to aplay with default (may conflict)
    if shutil.which('aplay'):
        AUDIO_PLAYER = 'aplay'
        AUDIO_ARGS = ['-D', 'default']
        logger.warning("Using aplay with default (may conflict with daemon)")
        return

    logger.error("No audio player found!")


async def play_wav(wav_data: bytes) -> bool:
    """Play WAV using available audio player."""
    if not AUDIO_PLAYER:
        logger.error("No audio player available")
        return False

    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_data)
            temp_path = f.name

        cmd = [AUDIO_PLAYER] + AUDIO_ARGS + [temp_path]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        os.unlink(temp_path)

        if proc.returncode != 0:
            logger.error(f"{AUDIO_PLAYER} error: {stderr.decode()}")
            return False
        return True

    except Exception as e:
        logger.error(f"Audio playback error: {e}")
        return False


async def handle_play(request):
    """Handle POST /play with WAV data."""
    try:
        wav_data = await request.read()
        logger.info(f"Received {len(wav_data)} bytes of audio")

        success = await play_wav(wav_data)

        if success:
            return web.json_response({"status": "ok"})
        else:
            return web.json_response({"status": "error"}, status=500)

    except Exception as e:
        logger.error(f"Play error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_status(request):
    """Handle GET /status."""
    return web.json_response({
        "service": "audio_server",
        "port": PORT,
        "player": AUDIO_PLAYER or "none"
    })


async def main():
    """Run the audio server."""
    find_audio_player()

    if not AUDIO_PLAYER:
        logger.error("No audio player found - server will not work")
        return

    app = web.Application()
    app.router.add_post('/play', handle_play)
    app.router.add_get('/status', handle_status)
    app.router.add_get('/', handle_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"Audio server running on http://0.0.0.0:{PORT}")
    logger.info("POST /play with WAV data to play audio")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
