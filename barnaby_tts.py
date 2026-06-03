"""Barnaby TTS — speaks in the cloned barnaby.wav voice and plays the
StartingVoice-Ending.wav sound effect before and after each reply."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ASSETS = Path(__file__).parent / "assets"
BARNABY_VOICE = str(ASSETS / "barnaby.wav")
BOOKEND_SOUND = str(ASSETS / "StartingVoice-Ending.wav")

TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


def _afplay(path: str) -> None:
    if path and Path(path).exists():
        subprocess.run(["afplay", path], check=False)


def play_bookend() -> None:
    """Play the intro/outro bat sound effect."""
    _afplay(BOOKEND_SOUND)


def speak(text: str) -> None:
    """Speak text in Barnaby's voice, wrapped in the bookend sound effect."""
    if not TTS_ENABLED or not text.strip():
        return
    try:
        from mlx_audio.tts.generate import generate_audio

        ref_audio = BARNABY_VOICE if Path(BARNABY_VOICE).exists() else None
        with tempfile.TemporaryDirectory() as td:
            generate_audio(
                text=text,
                model=TTS_MODEL,
                play=False,
                verbose=False,
                save=True,
                output_path=td,
                file_prefix="barnaby",
                ref_audio=ref_audio,
            )
            wav = next(Path(td).glob("*.wav"), None)
            play_bookend()
            if wav:
                _afplay(str(wav))
            play_bookend()
    except Exception as e:  # noqa: BLE001
        print(f"[barnaby-tts] error: {e}")
