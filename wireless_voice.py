#!/usr/bin/env python3
"""
Reachy Mini Wireless Voice Client
=================================

Full wireless audio via GStreamer WebRTC.
No SDK required - works with wireless daemon.

Usage:
  python3 wireless_voice.py --host 10.0.0.68
"""

import os
import sys
import asyncio
import json
import time
import wave
import io
import socket
import argparse
import logging
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
import httpx

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(Path.home() / '.env')
except ImportError:
    pass

# GStreamer
try:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    gi.require_version("GstWebRTC", "1.0")
    from gi.repository import Gst, GLib, GstApp, GstWebRTC
    Gst.init([])
    GSTREAMER_AVAILABLE = True
except (ImportError, ValueError) as e:
    GSTREAMER_AVAILABLE = False
    print(f"Warning: GStreamer not available: {e}")

# For finding producer
try:
    from gst_signalling.utils import async_find_producer_peer_id_by_name
    GST_SIGNALLING_AVAILABLE = True
except ImportError:
    GST_SIGNALLING_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    robot_host: str = "10.0.0.68"
    webrtc_port: int = 8443
    rtp_port: int = 5000
    http_port: int = 8000

    clawdbot_endpoint: str = os.environ.get("CLAWDBOT_ENDPOINT", "http://localhost:18789/v1/chat/completions")
    clawdbot_token: str = os.environ.get("CLAWDBOT_TOKEN", "REDACTED_CLAWDBOT_TOKEN")
    clawdbot_model: str = os.environ.get("CLAWDBOT_MODEL", "claude-sonnet-4-20250514")
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "REDACTED_VOICE_ID")


class AudioBuffer:
    """VAD-based audio accumulator."""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.frames: list[bytes] = []
        self.is_speaking = False
        self.silence_frames = 0
        self.speech_frames = 0
        self.lock = threading.Lock()
        self.energy_threshold = 500
        self.min_speech_frames = 5
        self.max_silence_frames = 25

    def add_frame(self, frame_bytes: bytes) -> Optional[bytes]:
        samples = np.frombuffer(frame_bytes, dtype=np.int16)
        energy = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

        with self.lock:
            if energy > self.energy_threshold:
                self.speech_frames += 1
                self.silence_frames = 0
                if self.speech_frames >= self.min_speech_frames:
                    self.is_speaking = True
            else:
                self.silence_frames += 1

            if self.is_speaking:
                self.frames.append(frame_bytes)
                if self.silence_frames >= self.max_silence_frames:
                    audio = self._get_audio()
                    self._reset()
                    return audio
        return None

    def _get_audio(self) -> bytes:
        if not self.frames:
            return b""
        all_audio = b''.join(self.frames)
        samples = np.frombuffer(all_audio, dtype=np.int16)
        if self.sample_rate == 48000:
            samples = samples[::3]
            out_rate = 16000
        else:
            out_rate = self.sample_rate
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(out_rate)
            wf.writeframes(samples.tobytes())
        buf.seek(0)
        return buf.read()

    def _reset(self):
        self.frames = []
        self.is_speaking = False
        self.silence_frames = 0
        self.speech_frames = 0


class WirelessVoiceClient:
    """Voice client using webrtcsrc for WebRTC audio."""

    def __init__(self, config: Config):
        self.config = config
        self.audio_buffer = AudioBuffer()
        self.running = False
        self.is_processing = False
        self.http_client = None
        self.pipeline = None
        self.main_loop = None

    def _on_audio_sample(self, appsink) -> Gst.FlowReturn:
        if self.is_processing:
            return Gst.FlowReturn.OK

        sample = appsink.emit("pull-sample")
        if sample:
            buffer = sample.get_buffer()
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if success:
                audio_data = self.audio_buffer.add_frame(bytes(map_info.data))
                buffer.unmap(map_info)
                if audio_data:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        lambda ad=audio_data: asyncio.create_task(self._process_speech(ad))
                    )
        return Gst.FlowReturn.OK

    async def _process_speech(self, audio_data: bytes):
        if self.is_processing:
            return
        self.is_processing = True

        try:
            logger.info(f"🎤 Processing speech ({len(audio_data)} bytes)")

            transcript = await self._transcribe(audio_data)
            if not transcript:
                return
            logger.info(f"📝 Heard: \"{transcript}\"")

            response, tool_calls = await self._chat(transcript)
            if not response and not tool_calls:
                return

            for tool_call in tool_calls:
                await self._execute_tool(tool_call)

            if response:
                logger.info(f"💬 Response: \"{response}\"")
                await self._speak(response)

        except Exception as e:
            logger.error(f"Processing error: {e}")
        finally:
            self.is_processing = False

    async def _transcribe(self, audio_data: bytes) -> Optional[str]:
        if not self.config.openai_api_key:
            return None
        try:
            response = await self.http_client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                files={"file": ("audio.wav", audio_data, "audio/wav")},
                data={"model": "whisper-1", "language": "en"},
            )
            if response.status_code == 200:
                text = response.text.strip()
                if text and text.lower() not in ['', 'you', 'thank you.', 'thanks.', 'bye.']:
                    return text
        except Exception as e:
            logger.error(f"Transcription error: {e}")
        return None

    async def _chat(self, user_message: str) -> tuple[Optional[str], list]:
        system_prompt = """You are KayaCan, a robot. Keep responses SHORT - 1-2 sentences. Be warm. No emojis."""

        tools = [
            {"type": "function", "function": {"name": "play_emotion", "parameters": {"type": "object", "properties": {"emotion": {"type": "string", "enum": ["happy", "sad", "surprised"]}}}}},
        ]

        payload = {
            "model": self.config.clawdbot_model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            "tools": tools,
            "max_tokens": 150
        }

        try:
            response = await self.http_client.post(
                self.config.clawdbot_endpoint,
                headers={"Authorization": f"Bearer {self.config.clawdbot_token}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and data["choices"]:
                    msg = data["choices"][0].get("message", {})
                    return msg.get("content") or "", msg.get("tool_calls", [])
        except Exception as e:
            logger.error(f"Chat error: {e}")
        return None, []

    async def _execute_tool(self, tool_call: dict):
        func = tool_call.get("function", {})
        name = func.get("name")
        try:
            args = json.loads(func.get("arguments", "{}"))
        except:
            args = {}

        base_url = f"http://{self.config.robot_host}:{self.config.http_port}/api"
        try:
            if name == "play_emotion":
                emotion = args.get("emotion", "happy")
                await self.http_client.post(f"{base_url}/move/play/recorded-move-dataset/pollen-robotics/reachy_mini_emotions/{emotion}")
                logger.info(f"🎭 Emotion: {emotion}")
        except Exception as e:
            logger.error(f"Tool error: {e}")

    async def _speak(self, text: str):
        if not self.config.elevenlabs_api_key:
            logger.info(f"[Would speak]: {text}")
            return
        try:
            response = await self.http_client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}",
                headers={"xi-api-key": self.config.elevenlabs_api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_turbo_v2", "output_format": "pcm_24000"},
            )
            if response.status_code == 200:
                logger.info(f"🔊 Got TTS audio ({len(response.content)} bytes)")
                # TODO: Send via RTP to robot speaker
        except Exception as e:
            logger.error(f"TTS error: {e}")

    async def run(self):
        self.running = True
        self.http_client = httpx.AsyncClient(timeout=30.0)

        logger.info("=" * 50)
        logger.info("Reachy Mini Wireless Voice Client")
        logger.info(f"Robot: {self.config.robot_host}")
        logger.info("=" * 50)

        try:
            # Find producer
            logger.info("Finding WebRTC producer...")
            peer_id = await async_find_producer_peer_id_by_name(
                self.config.robot_host, self.config.webrtc_port, "reachymini"
            )
            logger.info(f"Found producer: {peer_id}")

            # Build pipeline using webrtcsrc
            pipeline_str = f"""
                webrtcsrc name=webrtc
                    signaller::uri=ws://{self.config.robot_host}:{self.config.webrtc_port}
                    signaller::producer-peer-id={peer_id}
                webrtc. ! queue ! decodebin ! audioconvert ! audioresample
                    ! audio/x-raw,format=S16LE,channels=1,rate=48000
                    ! appsink name=audiosink emit-signals=true sync=false
            """

            logger.info("Creating GStreamer pipeline...")
            self.pipeline = Gst.parse_launch(pipeline_str)

            appsink = self.pipeline.get_by_name("audiosink")
            appsink.connect("new-sample", self._on_audio_sample)

            # Handle pipeline errors
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", self._on_error)
            bus.connect("message::state-changed", self._on_state_changed)

            self.pipeline.set_state(Gst.State.PLAYING)

            # Run GLib main loop
            self.main_loop = GLib.MainLoop()
            loop_thread = threading.Thread(target=self.main_loop.run, daemon=True)
            loop_thread.start()

            logger.info("✅ Pipeline started!")
            logger.info("🎤 Listening... (speak to the robot)")

            while self.running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
            if self.main_loop:
                self.main_loop.quit()
            await self.http_client.aclose()

    def _on_error(self, bus, message):
        err, debug = message.parse_error()
        logger.error(f"Pipeline error: {err.message}")
        logger.debug(f"Debug: {debug}")

    def _on_state_changed(self, bus, message):
        if message.src == self.pipeline:
            old, new, pending = message.parse_state_changed()
            logger.debug(f"Pipeline state: {old.value_nick} -> {new.value_nick}")


async def main():
    parser = argparse.ArgumentParser(description="Reachy Mini Wireless Voice")
    parser.add_argument("--host", default="10.0.0.68", help="Robot IP")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not GSTREAMER_AVAILABLE:
        print("ERROR: GStreamer required")
        sys.exit(1)

    config = Config(robot_host=args.host)
    client = WirelessVoiceClient(config)
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
