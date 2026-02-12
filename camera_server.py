#!/usr/bin/env python3
"""Simple HTTP camera server for Reachy Mini.

Serves camera snapshots via HTTP without requiring the SDK.
Uses rpicam-still for Raspberry Pi camera capture.
Run this on the robot alongside talk_wireless.py.

Usage:
    python3 camera_server.py
"""

import asyncio
import logging
import subprocess
import tempfile
import os
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PORT = 9001


class CameraServer:
    """Simple HTTP server that serves camera snapshots using rpicam-still."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._available = False

    async def start(self):
        """Check if rpicam-still is available."""
        try:
            result = subprocess.run(['which', 'rpicam-still'], capture_output=True)
            self._available = result.returncode == 0
            if self._available:
                logger.info("Camera available (rpicam-still)")
            else:
                logger.error("rpicam-still not found")
            return self._available
        except Exception as e:
            logger.error(f"Camera check failed: {e}")
            return False

    async def stop(self):
        """Nothing to release."""
        pass

    async def capture_jpeg(self) -> bytes | None:
        """Capture a frame using rpicam-still."""
        if not self._available:
            return None

        async with self._lock:
            try:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                    temp_path = f.name

                # Capture with rpicam-still (optimized for low light)
                proc = await asyncio.create_subprocess_exec(
                    'rpicam-still',
                    '-n',  # No preview
                    '-t', '500',  # Allow auto-exposure time
                    '--width', '640',
                    '--height', '480',
                    '--ev', '2',  # Exposure compensation +2 stops
                    '--gain', '16',  # High gain for low light
                    '--shutter', '100000',  # 100ms shutter (longer exposure)
                    '--awb', 'auto',  # Auto white balance
                    '-q', '85',  # JPEG quality
                    '-o', temp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=5.0)

                if os.path.exists(temp_path):
                    with open(temp_path, 'rb') as f:
                        jpeg_data = f.read()
                    os.unlink(temp_path)
                    if jpeg_data:
                        return jpeg_data

            except asyncio.TimeoutError:
                logger.warning("Camera capture timed out")
            except Exception as e:
                logger.warning(f"Camera capture error: {e}")

        return None

    async def handle_snapshot(self, request):
        """Handle /snapshot endpoint."""
        jpeg = await self.capture_jpeg()
        if jpeg:
            return web.Response(body=jpeg, content_type='image/jpeg')
        return web.Response(status=503, text="Camera not available")

    async def handle_status(self, request):
        """Handle /status endpoint."""
        return web.json_response({
            "service": "camera_server",
            "camera_available": self._available,
            "port": PORT,
        })


async def main():
    """Run the camera server."""
    camera = CameraServer()

    if not await camera.start():
        logger.error("Failed to start camera")
        return

    app = web.Application()
    app.router.add_get('/snapshot', camera.handle_snapshot)
    app.router.add_get('/status', camera.handle_status)
    app.router.add_get('/', camera.handle_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"Camera server running on http://0.0.0.0:{PORT}")
    logger.info("Endpoints: /snapshot (JPEG), /status (JSON)")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await camera.stop()
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
