"""Main note-taking app: VAD-driven recording, STT, LLM cleanup, live Rich UI."""

from __future__ import annotations

import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import llm_processor as llm
import note_store
import tts_reader
from reachy_gestures import RobotState, get_gestures, init_gestures

load_dotenv()

SAMPLE_RATE = 16000
BLOCK_MS = 32
BLOCK_SAMPLES = SAMPLE_RATE * BLOCK_MS // 1000
AUTO_SAVE_SILENCE = float(os.getenv("AUTO_SAVE_SILENCE_SECONDS", "30"))

console = Console()


@dataclass
class SessionState:
    started_at: float = field(default_factory=time.time)
    notes_saved: int = 0
    current_raw: list[str] = field(default_factory=list)   # raw transcripts this note
    current_clean: list[str] = field(default_factory=list) # cleaned chunks this note
    current_tags: list[str] = field(default_factory=list)
    status: str = "idle"  # idle | listening | processing | writing | saving
    last_speech_at: float = field(default_factory=time.time)
    session_notes: list[str] = field(default_factory=list) # finalized note bodies

    @property
    def duration(self) -> float:
        return time.time() - self.started_at

    @property
    def word_count(self) -> int:
        return sum(len(c.split()) for c in self.current_clean)

    @property
    def current_body(self) -> str:
        return "\n\n".join(self.current_clean).strip()


# --- Audio / VAD plumbing -------------------------------------------------

class VADRecorder:
    """Silero VAD-driven recorder. Yields (audio_np, energy) per utterance."""

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad, VADIterator

        self.torch = torch
        self.model = load_silero_vad()
        self.iterator = VADIterator(self.model, sampling_rate=SAMPLE_RATE)
        self._buffer: list[np.ndarray] = []
        self._in_speech = False
        self.energy = 0.0

    def feed(self, block: np.ndarray):
        """Feed an audio block. Returns finished utterance (np.float32) or None."""
        # Silero VAD wants 512 samples at 16kHz
        x = self.torch.from_numpy(block).float()
        self.energy = float(np.sqrt(np.mean(block ** 2)))
        # Chunk into 512-sample frames
        finished = None
        for i in range(0, len(x) - 511, 512):
            frame = x[i : i + 512]
            ev = self.iterator(frame, return_seconds=False)
            if ev is not None:
                if "start" in ev:
                    self._in_speech = True
                    self._buffer = []
                elif "end" in ev and self._in_speech:
                    self._in_speech = False
                    if self._buffer:
                        finished = np.concatenate(self._buffer)
                    self._buffer = []
            if self._in_speech:
                self._buffer.append(frame.numpy())
        return finished


class STTEngine:
    def __init__(self):
        from parakeet_mlx import from_pretrained

        self.model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")

    def transcribe(self, audio: np.ndarray) -> str:
        result = self.model.transcribe(audio)
        return getattr(result, "text", str(result)).strip()


# --- UI -------------------------------------------------------------------

def render(state: SessionState, live_partial: str) -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="status", size=3),
    )

    header = Panel(
        Text(
            f"voice-notes-local · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            style="bold cyan",
            justify="center",
        )
    )
    layout["header"].update(header)

    body = Layout()
    body.split_row(Layout(name="note", ratio=2), Layout(name="side", ratio=1))

    note_md = state.current_body or "_(no content yet)_"
    if live_partial:
        note_md += f"\n\n> {live_partial}"
    body["note"].update(Panel(Markdown(note_md), title="Current note", border_style="green"))

    stats = Table.grid(padding=(0, 1))
    stats.add_row("Duration", f"{int(state.duration)}s")
    stats.add_row("Words", str(state.word_count))
    stats.add_row("Saved this session", str(state.notes_saved))
    stats.add_row("Tags", ", ".join(state.current_tags) or "—")
    body["side"].update(Panel(stats, title="Session", border_style="blue"))

    layout["body"].update(body)

    colors = {"idle": "dim", "listening": "bold green", "processing": "yellow", "writing": "magenta", "saving": "cyan"}
    layout["status"].update(
        Panel(Text(f"● {state.status.upper()}", style=colors.get(state.status, "white")), border_style="grey50")
    )
    return layout


# --- Pipeline -------------------------------------------------------------

def _gesture(state: RobotState):
    g = get_gestures()
    if g:
        g.set_state(state)


def process_utterance(state: SessionState, raw_text: str, stt_finalize_session):
    cmd = llm.detect_voice_command(raw_text)
    if cmd:
        return handle_command(state, cmd, stt_finalize_session)

    state.status = "processing"
    _gesture(RobotState.PROCESSING)
    cleaned = llm.clean_transcript(raw_text)

    state.status = "writing"
    _gesture(RobotState.WRITING)
    g = get_gestures()
    if g:
        g.sync_to_note_length(len(cleaned.split()))
    structured = llm.structure_note(cleaned)

    state.current_raw.append(raw_text)
    state.current_clean.append(structured)
    state.last_speech_at = time.time()
    state.status = "idle"
    _gesture(RobotState.IDLE)


def handle_command(state: SessionState, cmd: dict, finalize):
    name = cmd["command"]
    if name == "new_note":
        finalize(state, save=True)
        _gesture(RobotState.CONFIRMING)
        tts_reader.confirm("Starting a new note.")
        _gesture(RobotState.IDLE)
    elif name == "save_note":
        finalize(state, save=True)
        _gesture(RobotState.CONFIRMING)
        tts_reader.confirm("Note saved.")
        _gesture(RobotState.IDLE)
    elif name == "cancel":
        state.current_raw.clear()
        state.current_clean.clear()
        state.current_tags.clear()
        _gesture(RobotState.CONFIRMING)
        tts_reader.confirm("Discarded.")
        _gesture(RobotState.IDLE)
    elif name == "read_back":
        _gesture(RobotState.READING_BACK)
        tts_reader.read_text(state.current_body or "There's nothing to read yet.")
        _gesture(RobotState.IDLE)
    elif name == "summarize":
        if state.session_notes or state.current_clean:
            corpus = state.session_notes + ([state.current_body] if state.current_body else [])
            _gesture(RobotState.SUMMARIZING)
            summary = llm.summarize_session(corpus)
            console.print(Panel(Markdown(summary), title="Session summary"))
            _gesture(RobotState.READING_BACK)
            tts_reader.read_text(summary)
            _gesture(RobotState.IDLE)
    elif name == "add_tag":
        if cmd.get("arg"):
            state.current_tags.append(cmd["arg"])
            _gesture(RobotState.CONFIRMING)
            tts_reader.confirm(f"Tagged {cmd['arg']}.")
            _gesture(RobotState.IDLE)


def finalize_note(state: SessionState, *, save: bool) -> None:
    if not state.current_clean:
        return
    body = state.current_body
    if save:
        state.status = "saving"
        title = llm.generate_title(body)
        path = note_store.save_note(
            body,
            title=title,
            tags=list(state.current_tags),
            duration=state.duration,
        )
        state.notes_saved += 1
        state.session_notes.append(body)
        console.print(f"[green]saved[/green] {path}")
    state.current_raw.clear()
    state.current_clean.clear()
    state.current_tags.clear()
    state.status = "idle"


# --- Main loop ------------------------------------------------------------

def main(robot: bool = False, external_stop: threading.Event = None):
    state = SessionState()
    audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)

    if robot:
        console.print("[bold cyan]Initializing Reachy Mini...[/bold cyan]")
        if not get_gestures():  # don't re-init if already set by app framework
            init_gestures()

    def on_audio(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())

    console.print("[bold]Loading VAD + STT...[/bold]")
    vad = VADRecorder()
    stt = STTEngine()
    console.print("[bold green]Ready. Speak when you like. Ctrl+C to stop.[/bold green]")

    stop_event = external_stop if external_stop is not None else threading.Event()

    def shutdown(signum, frame):
        stop_event.set()

    if external_stop is None:
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    live_partial = ""

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SAMPLES,
        callback=on_audio,
    ):
        with Live(render(state, live_partial), refresh_per_second=8, console=console) as live:
            while not stop_event.is_set():
                try:
                    block = audio_q.get(timeout=0.1)
                except queue.Empty:
                    block = None

                if block is not None:
                    utterance = vad.feed(block)
                    if vad._in_speech:
                        state.status = "listening"
                        g = get_gestures()
                        if g:
                            g.set_state(RobotState.LISTENING)
                            g.sync_to_audio_energy(vad.energy)
                    if utterance is not None and len(utterance) > SAMPLE_RATE // 2:
                        state.status = "processing"
                        live.update(render(state, "transcribing…"))
                        text = stt.transcribe(utterance)
                        if text:
                            live_partial = text
                            live.update(render(state, live_partial))
                            process_utterance(state, text, finalize_note)
                            live_partial = ""

                # Auto-save after long silence
                if (
                    state.current_clean
                    and not vad._in_speech
                    and time.time() - state.last_speech_at > AUTO_SAVE_SILENCE
                ):
                    finalize_note(state, save=True)

                if state.status == "listening" and not vad._in_speech:
                    state.status = "idle"

                live.update(render(state, live_partial))

    # Clean shutdown — save any open note
    console.print("\n[yellow]Shutting down — saving open note if any...[/yellow]")
    finalize_note(state, save=True)
    if state.session_notes:
        try:
            _gesture(RobotState.SUMMARIZING)
            summary = llm.summarize_session(state.session_notes)
            day_dir = note_store._today_dir()
            (day_dir / "session-summary.md").write_text(summary + "\n")
            console.print(f"[green]wrote session-summary.md[/green]")
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]summary failed:[/red] {e}")
    g = get_gestures()
    if g:
        g.stop()
    console.print("[bold]Bye.[/bold]")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="voice-notes-local")
    parser.add_argument("--robot", action="store_true", help="Enable Reachy Mini gesture sync")
    args = parser.parse_args()
    try:
        main(robot=args.robot)
    except KeyboardInterrupt:
        pass
    sys.exit(0)
