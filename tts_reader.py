"""Qwen3-TTS readback via mlx-audio. Falls back to silent no-op if disabled."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
VOICE_PRESET = os.path.expanduser(os.getenv("TTS_VOICE_PRESET", "~/.voice-notes-voice.wav"))
TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


def read_text(text: str) -> None:
    if not TTS_ENABLED or not text.strip():
        return
    try:
        from mlx_audio.tts.generate import generate_audio

        ref_audio = VOICE_PRESET if Path(VOICE_PRESET).exists() else None

        with tempfile.TemporaryDirectory() as td:
            generate_audio(
                text=text,
                model=TTS_MODEL,
                play=False,
                verbose=False,
                save=True,
                output_path=td,
                file_prefix="tts_out",
                ref_audio=ref_audio,
            )
            wav = next(Path(td).glob("*.wav"), None)
            if wav:
                subprocess.run(["afplay", str(wav)], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"[tts] error: {e}")


def read_note(filepath: str) -> None:
    from note_store import load_note

    note = load_note(filepath)
    title = note["frontmatter"].get("title", "Untitled")
    read_text(f"{title}. {note['body']}")


def confirm(message: str) -> None:
    read_text(message)


def speak_phonemes_with_callback(text: str, on_phoneme=None) -> None:
    """Phase 2 hook — TTS emits phoneme timing for gesture sync."""
    read_text(text)
