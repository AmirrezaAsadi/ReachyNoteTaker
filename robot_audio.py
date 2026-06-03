"""Route audio through the Reachy Mini's USB audio card (mic + speaker).

On a Reachy Mini Lite the robot exposes a "Reachy Mini Audio" device over USB
at 16 kHz — exactly what the VAD/STT pipeline wants. Set AUDIO_DEVICE in .env
to a name substring (default "Reachy Mini Audio"); leave it empty to fall back
to the system default mic/speakers.
"""

from __future__ import annotations

import os

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

AUDIO_DEVICE_NAME = os.getenv("AUDIO_DEVICE", "Reachy Mini Audio").strip()
TARGET_SR = 16000


def device_index() -> int | None:
    """Index of the configured audio device, or None for system default."""
    if not AUDIO_DEVICE_NAME:
        return None
    for i, d in enumerate(sd.query_devices()):
        if AUDIO_DEVICE_NAME.lower() in d["name"].lower():
            return i
    return None


def _to_mono_16k(data: np.ndarray, sr: int) -> np.ndarray:
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != TARGET_SR:
        n = int(len(data) * TARGET_SR / sr)
        data = np.interp(
            np.linspace(0, len(data), n, endpoint=False),
            np.arange(len(data)),
            data,
        ).astype("float32")
    return data.astype("float32")


def play_wav(path: str, blocking: bool = True) -> None:
    """Play a WAV file through the configured device (robot speaker)."""
    data, sr = sf.read(path, dtype="float32")
    data = _to_mono_16k(data, sr)
    sd.play(data, TARGET_SR, device=device_index(), blocking=blocking)
