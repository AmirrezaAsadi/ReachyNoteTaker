"""End-to-end smoke test for the voice-notes pipeline.

Reports load time, latency, and memory per stage. Pass/fail per test.
"""

from __future__ import annotations

import gc
import os
import resource
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf
from rich.console import Console
from rich.table import Table

console = Console()
RESULTS: list[tuple[str, bool, str, float, float]] = []


def _mem_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if os.uname().sysname == "Linux" else 1024)


def run(name: str, fn):
    gc.collect()
    m0 = _mem_mb()
    t0 = time.perf_counter()
    try:
        msg = fn() or "ok"
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        msg = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    dt = (time.perf_counter() - t0) * 1000
    dm = _mem_mb() - m0
    RESULTS.append((name, ok, msg, dt, dm))


def test_vad_loads():
    from silero_vad import load_silero_vad

    load_silero_vad()


def test_stt_loads():
    from parakeet_mlx import from_pretrained

    from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")


def test_llm_reachable():
    import llm_processor as llm

    out = llm.clean_transcript("um hello uh world")
    assert out, "empty clean_transcript output"
    return out[:60]


def test_tts_loads():
    import tts_reader

    eng = tts_reader._get_engine()
    if eng is None and tts_reader.TTS_ENABLED:
        raise RuntimeError("TTS enabled but engine failed to load")
    return "disabled" if not tts_reader.TTS_ENABLED else "loaded"


def test_mock_session():
    """Generate 1s of silence + a tone, run it through STT (won't transcribe well, but exercises path)."""
    from parakeet_mlx import from_pretrained

    model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")
    sr = 16000
    audio = np.zeros(sr * 2, dtype=np.float32)
    result = model.transcribe(audio)
    return f"text='{getattr(result, 'text', '')}'"


def test_llm_functions():
    import llm_processor as llm

    text = "today we discussed the new feature. action item: ship by friday"
    cleaned = llm.clean_transcript(text)
    structured = llm.structure_note(cleaned)
    title = llm.generate_title(cleaned)
    summary = llm.summarize_session([structured])
    cmd = llm.detect_voice_command("save note")
    assert cmd and cmd["command"] == "save_note", f"command detection failed: {cmd}"
    return f"title='{title[:30]}'"


def test_note_cycle():
    import note_store

    with tempfile.TemporaryDirectory() as td:
        os.environ["NOTES_DIR"] = td
        # Reload module-level constants
        import importlib

        importlib.reload(note_store)

        path = note_store.save_note(
            "Test body about robots.",
            title="Robot test",
            tags=["test"],
            summary="A test.",
            duration=1.0,
        )
        loaded = note_store.load_note(path)
        assert loaded["frontmatter"]["title"] == "Robot test"
        hits = note_store.search_notes("robots")
        assert hits, "search returned no hits"
        listed = note_store.list_notes(tag="test")
        assert listed, "tag listing empty"
    return f"saved={path.name}"


def main():
    run("VAD loads",         test_vad_loads)
    run("STT loads",         test_stt_loads)
    run("LLM reachable",     test_llm_reachable)
    run("TTS loads",         test_tts_loads)
    run("Mock STT session",  test_mock_session)
    run("LLM functions",     test_llm_functions)
    run("Note save/load/search", test_note_cycle)

    table = Table(title="Pipeline test results")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Latency (ms)", justify="right")
    table.add_column("Δ Mem (MB)", justify="right")
    table.add_column("Detail")
    passed = 0
    for name, ok, msg, dt, dm in RESULTS:
        table.add_row(
            name,
            "[green]PASS[/green]" if ok else "[red]FAIL[/red]",
            f"{dt:.0f}",
            f"{dm:+.1f}",
            msg[:80],
        )
        passed += int(ok)
    console.print(table)
    console.print(f"\n{passed}/{len(RESULTS)} passed.")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
