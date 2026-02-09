"""Main entry point for the Reachy agent - Clawdbot brain with ElevenLabs voice."""

import asyncio
import faulthandler
import logging
import signal
import sys

from reachy_agent import ReachyAgent
from reachy_agent.config import Config

# Enable faulthandler to get tracebacks on native crashes
faulthandler.enable()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Quiet noisy libraries
logging.getLogger("reachy_mini").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Debug our components
logging.getLogger("reachy_agent.agent").setLevel(logging.DEBUG)
logging.getLogger("reachy_agent.clawdbot").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

MAX_RESTARTS = 5
RESTART_DELAY_SECONDS = 2


async def run_agent(config: Config, shutdown_event: asyncio.Event) -> bool:
    """Run agent once. Returns True if should restart, False if clean shutdown."""
    agent = ReachyAgent(config)
    agent_task = asyncio.create_task(agent.run())

    try:
        await asyncio.wait(
            [agent_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if shutdown_event.is_set():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
            return False  # Clean shutdown, don't restart

        # Agent exited on its own - check if it crashed
        if agent_task.done():
            exc = agent_task.exception()
            if exc:
                logger.error(f"Agent crashed: {exc}")
                return True  # Restart
        return False

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return True  # Restart
    finally:
        await agent.stop()


async def main() -> None:
    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("")
        logger.error("Required environment variables:")
        logger.error("  OPENAI_API_KEY     - For Whisper STT")
        logger.error("  ELEVENLABS_API_KEY - For TTS")
        logger.error("")
        logger.error("Optional:")
        logger.error("  CLAWDBOT_ENDPOINT  - Default: http://localhost:18789/v1/chat/completions")
        logger.error("  CLAWDBOT_TOKEN     - Your Clawdbot token")
        logger.error("  ELEVENLABS_VOICE_ID - Default: Rachel")
        logger.error("  HONCHO_API_KEY     - For persistent memory")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Reachy Mini Agent - Clawdbot + ElevenLabs")
    logger.info("=" * 60)
    logger.info(f"Clawdbot: {config.clawdbot_endpoint}")
    logger.info(f"ElevenLabs Voice: {config.elevenlabs_voice_id}")
    logger.info(f"Honcho: {'enabled' if config.honcho_api_key else 'disabled'}")
    logger.info("=" * 60)

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Shutting down gracefully...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    restarts = 0
    while not shutdown_event.is_set():
        should_restart = await run_agent(config, shutdown_event)

        if not should_restart or shutdown_event.is_set():
            break

        restarts += 1
        if restarts >= MAX_RESTARTS:
            logger.error(f"Max restarts ({MAX_RESTARTS}) reached, giving up")
            break

        logger.info(f"Restarting agent in {RESTART_DELAY_SECONDS}s (attempt {restarts}/{MAX_RESTARTS})...")
        await asyncio.sleep(RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
