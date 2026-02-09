#!/usr/bin/env python3
"""Direct SDK audio player - no bridge, no distortion."""
import sys
import wave
import time
import numpy as np

sys.path.insert(0, '/restore/venvs/mini_daemon/lib/python3.12/site-packages')
from reachy_mini import ReachyMini

def play_wav(wav_path):
    robot = ReachyMini(media_backend="default")
    
    with wave.open(wav_path, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        sr = wf.getframerate()
        nc = wf.getnchannels()
        sw = wf.getsampwidth()
    
    # Convert to float32 normalized
    if sw == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        audio = np.frombuffer(frames, dtype=np.int8).astype(np.float32) / 128.0
    
    # SDK expects stereo
    if nc == 1:
        audio = np.column_stack([audio, audio])
    elif nc == 2:
        audio = audio.reshape(-1, 2)
    
    print(f"Playing {len(audio)} samples at {sr}Hz...")
    
    robot.media.start_playing()
    robot.media.push_audio_sample(audio)
    time.sleep(len(audio) / sr + 0.5)
    robot.media.stop_playing()
    print("Done!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: play_audio.py <wav_file>")
        sys.exit(1)
    play_wav(sys.argv[1])
