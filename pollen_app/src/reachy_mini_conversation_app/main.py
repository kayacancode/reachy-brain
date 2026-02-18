"""Entrypoint for the Reachy Mini conversation app."""

import os
import sys
import time
import asyncio
import argparse
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load .env from package directory before anything else
_pkg_dir = Path(__file__).parent
_env_file = _pkg_dir / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(_env_file), override=True)
    print(f"[main.py] Loaded .env from {_env_file}")

import gradio as gr
from fastapi import FastAPI
from fastrtc import Stream
from gradio.utils import get_space

from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini_conversation_app.utils import (
    parse_args,
    setup_logger,
    handle_vision_stuff,
    log_connection_troubleshooting,
)


def update_chatbot(chatbot: List[Dict[str, Any]], response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Update the chatbot with AdditionalOutputs."""
    chatbot.append(response)
    return chatbot


def main() -> None:
    """Entrypoint for the Reachy Mini conversation app."""
    args, _ = parse_args()
    run(args)


def run(
    args: argparse.Namespace,
    robot: ReachyMini = None,
    app_stop_event: Optional[threading.Event] = None,
    settings_app: Optional[FastAPI] = None,
    instance_path: Optional[str] = None,
) -> None:
    """Run the Reachy Mini conversation app."""
    # Putting these dependencies here makes the dashboard faster to load when the conversation app is installed
    from reachy_mini_conversation_app.moves import MovementManager
    from reachy_mini_conversation_app.console import LocalStream
    from reachy_mini_conversation_app.openai_realtime import OpenaiRealtimeHandler
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
    from reachy_mini_conversation_app.audio.head_wobbler import HeadWobbler

    logger = setup_logger(args.debug)
    logger.info("Starting Reachy Mini Conversation App")

    if args.no_camera and args.head_tracker is not None:
        logger.warning(
            "Head tracking disabled: --no-camera flag is set. "
            "Remove --no-camera to enable head tracking."
        )

    # Check if using Clawdbot mode (need to know early for SDK config)
    use_clawdbot_env = os.getenv("USE_CLAWDBOT", "").lower() in ("1", "true", "yes")
    use_clawdbot = args.clawdbot or use_clawdbot_env

    if robot is None:
        try:
            robot_kwargs = {}
            if args.robot_name is not None:
                robot_kwargs["robot_name"] = args.robot_name

            # For Clawdbot mode with Gradio, disable SDK media (Gradio handles browser audio)
            if use_clawdbot and args.gradio:
                robot_kwargs["media_backend"] = "no_media"
                logger.info("Initializing ReachyMini with no_media backend (Gradio handles audio)")
            else:
                logger.info("Initializing ReachyMini (SDK will auto-detect appropriate backend)")
            robot = ReachyMini(**robot_kwargs)

        except TimeoutError as e:
            logger.error(
                "Connection timeout: Failed to connect to Reachy Mini daemon. "
                f"Details: {e}"
            )
            log_connection_troubleshooting(logger, args.robot_name)
            sys.exit(1)

        except ConnectionError as e:
            logger.error(
                "Connection failed: Unable to establish connection to Reachy Mini. "
                f"Details: {e}"
            )
            log_connection_troubleshooting(logger, args.robot_name)
            sys.exit(1)

        except Exception as e:
            logger.error(
                f"Unexpected error during robot initialization: {type(e).__name__}: {e}"
            )
            logger.error("Please check your configuration and try again.")
            sys.exit(1)

    # Check if running in simulation mode without --gradio
    if robot.client.get_status()["simulation_enabled"] and not args.gradio:
        logger.error(
            "Simulation mode requires Gradio interface. Please use --gradio flag when running in simulation mode."
        )
        robot.client.disconnect()
        sys.exit(1)

    camera_worker, _, vision_manager = handle_vision_stuff(args, robot)

    # Initialize face identity for user recognition (use_clawdbot defined above)
    # Works with either SDK camera_worker or HTTP fallback
    face_identity = None
    if use_clawdbot:
        try:
            from reachy_mini_conversation_app.face_identity_manager import FaceIdentityManager
            robot_ip = os.getenv("ROBOT_IP")
            face_identity = FaceIdentityManager(
                camera_worker=camera_worker,  # May be None if --no-camera
                robot_ip=robot_ip,  # For HTTP fallback
            )
            logger.info("Face identity manager initialized")
        except Exception as e:
            logger.warning(f"Face identity disabled: {e}")

    movement_manager = MovementManager(
        current_robot=robot,
        camera_worker=camera_worker,
    )

    head_wobbler = HeadWobbler(set_speech_offsets=movement_manager.set_speech_offsets)

    # Initialize Honcho memory if using Clawdbot
    memory = None
    if args.clawdbot:
        honcho_api_key = os.getenv("HONCHO_API_KEY")
        if honcho_api_key:
            try:
                # Import and initialize memory
                from reachy_mini_conversation_app.clawdbot_handler import ClawdbotConfig
                # We'll initialize memory in the handler, just check config is valid
                logger.info("Honcho memory will be initialized in ClawdbotHandler")
            except Exception as e:
                logger.warning(f"Honcho memory initialization skipped: {e}")

    deps = ToolDependencies(
        reachy_mini=robot,
        movement_manager=movement_manager,
        camera_worker=camera_worker,
        vision_manager=vision_manager,
        head_wobbler=head_wobbler,
        memory=memory,
        face_identity=face_identity,
    )
    current_file_path = os.path.dirname(os.path.abspath(__file__))
    logger.debug(f"Current file absolute path: {current_file_path}")
    chatbot = gr.Chatbot(
        type="messages",
        resizable=True,
        avatar_images=(
            os.path.join(current_file_path, "images", "user_avatar.png"),
            os.path.join(current_file_path, "images", "reachymini_avatar.png"),
        ),
    )
    logger.debug(f"Chatbot avatar images: {chatbot.avatar_images}")

    # Choose handler based on --clawdbot flag or USE_CLAWDBOT env var (already computed above)
    print(f"[main.py] USE_CLAWDBOT env={use_clawdbot_env}, args.clawdbot={args.clawdbot}, use_clawdbot={use_clawdbot}")
    if use_clawdbot:
        from reachy_mini_conversation_app.clawdbot_handler import ClawdbotHandler, ClawdbotConfig
        clawdbot_config = ClawdbotConfig.from_env()
        handler = ClawdbotHandler(clawdbot_config, deps, gradio_mode=args.gradio)
        logger.info("Using ClawdbotHandler (Claude + ElevenLabs + Honcho)")
        print("[main.py] *** USING CLAWDBOT HANDLER ***")
    else:
        handler = OpenaiRealtimeHandler(deps, gradio_mode=args.gradio, instance_path=instance_path)
        print("[main.py] Using OpenAI Realtime Handler")

    stream_manager: gr.Blocks | LocalStream | None = None

    if args.gradio:
        from reachy_mini_conversation_app.gradio_personality import PersonalityUI

        personality_ui = PersonalityUI()
        personality_ui.create_components()

        # Only show API key textbox for OpenAI Realtime mode
        additional_inputs = [chatbot]
        if not use_clawdbot:
            api_key_textbox = gr.Textbox(
                label="OPENAI API Key",
                type="password",
                value=os.getenv("OPENAI_API_KEY") if not get_space() else "",
            )
            additional_inputs.append(api_key_textbox)
        additional_inputs.extend(personality_ui.additional_inputs_ordered())

        stream = Stream(
            handler=handler,
            mode="send-receive",
            modality="audio",
            additional_inputs=additional_inputs,
            additional_outputs=[chatbot],
            additional_outputs_handler=update_chatbot,
            ui_args={"title": f"Talk with {os.environ.get('AGENT_NAME', 'Reachy')}" if use_clawdbot else "Talk with Reachy Mini"},
        )
        stream_manager = stream.ui
        if not settings_app:
            app = FastAPI()
        else:
            app = settings_app

        personality_ui.wire_events(handler, stream_manager)

        # Mount Gradio at /chat to avoid conflict with headless settings UI
        app = gr.mount_gradio_app(app, stream.ui, path="/chat")
    else:
        # In headless mode, wire settings_app + instance_path to console LocalStream
        stream_manager = LocalStream(
            handler,
            robot,
            settings_app=settings_app,
            instance_path=instance_path,
        )

    # Each async service → its own thread/loop
    movement_manager.start()
    # Only start HeadWobbler for OpenAI Realtime mode (Clawdbot has its own animation)
    if not use_clawdbot:
        head_wobbler.start()
    if camera_worker:
        camera_worker.start()
    if vision_manager:
        vision_manager.start()
    if face_identity:
        face_identity.start()

    def poll_stop_event() -> None:
        """Poll the stop event to allow graceful shutdown."""
        if app_stop_event is not None:
            app_stop_event.wait()

        logger.info("App stop event detected, shutting down...")
        try:
            stream_manager.close()
        except Exception as e:
            logger.error(f"Error while closing stream manager: {e}")

    if app_stop_event:
        threading.Thread(target=poll_stop_event, daemon=True).start()

    try:
        # Launch with external access on port 7862 for Clawdbot/Gradio mode
        # share=True creates HTTPS tunnel for microphone access
        if args.gradio and use_clawdbot:
            stream_manager.launch(server_name="0.0.0.0", server_port=7862, share=True)
        else:
            stream_manager.launch()
    except KeyboardInterrupt:
        logger.info("Keyboard interruption in main thread... closing server.")
    finally:
        movement_manager.stop()
        head_wobbler.stop()
        if camera_worker:
            camera_worker.stop()
        if vision_manager:
            vision_manager.stop()
        if face_identity:
            face_identity.stop()

        # Ensure media is explicitly closed before disconnecting
        try:
            robot.media.close()
        except Exception as e:
            logger.debug(f"Error closing media during shutdown: {e}")

        # prevent connection to keep alive some threads
        robot.client.disconnect()
        time.sleep(1)
        logger.info("Shutdown complete.")


class ReachyMiniConversationApp(ReachyMiniApp):  # type: ignore[misc]
    """Reachy Mini Apps entry point for the conversation app."""

    custom_app_url = "http://0.0.0.0:7860/"
    dont_start_webserver = False

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """Run the Reachy Mini conversation app."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        args, _ = parse_args()

        # is_wireless = reachy_mini.client.get_status()["wireless_version"]
        # args.head_tracker = None if is_wireless else "mediapipe"

        instance_path = self._get_instance_path().parent
        run(
            args,
            robot=reachy_mini,
            app_stop_event=stop_event,
            settings_app=self.settings_app,
            instance_path=instance_path,
        )


if __name__ == "__main__":
    app = ReachyMiniConversationApp()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
