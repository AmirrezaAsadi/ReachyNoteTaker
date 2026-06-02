"""Qwen3-TTS readback via mlx-audio. Falls back to silent no-op if disabled."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
VOICE_PRESET = os.path.expanduser(os.getenv("TTS_VOICE_PRESET", "~/.voice-notes-voice.qvp"))

_engine = None


def _get_engine():
    global _engine
    if _engine is not None or not TTS_ENABLED:
        return _engine
    try:
        from mlx_audio.tts import Qwen3TTS  # type: ignore

        kwargs = {}
        if Path(VOICE_PRESET).exists():
            kwargs["voice_preset"] = VOICE_PRESET
        _engine = Qwen3TTS(model="Qwen/Qwen3-TTS-1.7B", **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"[tts] disabled: {e}")
        _engine = None
    return _engine


def read_text(text: str) -> None:
    if not TTS_ENABLED or not text.strip():
        return
    eng = _get_engine()
    if eng is None:
        return
    eng.speak(text)


def read_note(filepath: str) -> None:
    from note_store import load_note

    note = load_note(filepath)
    title = note["frontmatter"].get("title", "Untitled")
    read_text(f"{title}. {note['body']}")


def confirm(message: str) -> None:
    """Short spoken confirmation."""
    read_text(message)


def speak_phonemes_with_callback(text: str, on_phoneme=None) -> None:
    """Phase 2 hook — TTS emits phoneme timing for gesture sync."""
    if not TTS_ENABLED:
        return
    eng = _get_engine()
    if eng is None:
        return
    # mlx-audio API placeholder; the real call will stream phoneme timestamps.
    if hasattr(eng, "speak_streaming"):
        for chunk in eng.speak_streaming(text):
            if on_phoneme and "phoneme" in chunk:
                on_phoneme(chunk["phoneme"], chunk["t"])
    else:
        eng.speak(text)
