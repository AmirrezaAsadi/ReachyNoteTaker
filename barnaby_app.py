"""Barnaby Bat conversation companion.

VAD-driven loop: listen -> STT -> in-character LLM reply -> Barnaby-voice TTS
(wrapped in the bat sound effect) -> Reachy Mini gestures. Saves the full
conversation transcript to a dated markdown file.
"""

from __future__ import annotations

import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

import barnaby_tts
import robot_audio
from barnaby_persona import BarnabyConversation
from note_taker import VADRecorder, STTEngine, SAMPLE_RATE, BLOCK_SAMPLES
from reachy_gestures import RobotState, get_gestures, init_gestures

load_dotenv()

console = Console()

NOTES_DIR = Path(os.path.expanduser(os.getenv("NOTES_DIR", "~/voice-notes")))
TRANSCRIPT_DIR = NOTES_DIR / "barnaby"


@dataclass
class ChatState:
    started_at: float = field(default_factory=time.time)
    exchanges: list[tuple[str, str]] = field(default_factory=list)  # (user, barnaby)
    status: str = "idle"

    @property
    def duration(self) -> float:
        return time.time() - self.started_at


def _gesture(state: RobotState):
    g = get_gestures()
    if g:
        g.set_state(state)


def save_transcript(state: ChatState) -> Path | None:
    if not state.exchanges:
        return None
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H-%M-%S")
    path = TRANSCRIPT_DIR / f"chat-{date.today().isoformat()}-{ts}.md"
    lines = [
        "---",
        f"title: Chat with Barnaby",
        f"date: {datetime.now().isoformat(timespec='seconds')}",
        f"duration: {int(state.duration)}",
        f"exchanges: {len(state.exchanges)}",
        "---",
        "",
        "# 🦇 Conversation with Barnaby",
        "",
    ]
    for user, bat in state.exchanges:
        lines.append(f"**You:** {user}")
        lines.append("")
        lines.append(f"**Barnaby:** {bat}")
        lines.append("")
    path.write_text("\n".join(lines))
    return path


def render(state: ChatState, live_partial: str) -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="status", size=3),
    )
    layout["header"].update(
        Panel(Text("🦇 Barnaby the Bat 🦇", style="bold magenta", justify="center"))
    )

    convo = Text()
    for user, bat in state.exchanges[-6:]:
        convo.append("You: ", style="bold cyan")
        convo.append(user + "\n")
        convo.append("Barnaby: ", style="bold magenta")
        convo.append(bat + "\n\n")
    if live_partial:
        convo.append("…" + live_partial, style="dim italic")
    layout["body"].update(Panel(convo, title="Conversation", border_style="magenta"))

    colors = {"idle": "dim", "listening": "bold green", "thinking": "yellow", "speaking": "cyan"}
    layout["status"].update(
        Panel(Text(f"● {state.status.upper()}", style=colors.get(state.status, "white")))
    )
    return layout


def main(robot: bool = False, external_stop: threading.Event = None):
    state = ChatState()
    convo = BarnabyConversation()
    audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)

    if robot and not get_gestures():
        init_gestures()

    def on_audio(indata, frames, time_info, status):
        try:
            audio_q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # drop frames while busy (e.g. while Barnaby is speaking)

    def drain_mic():
        """Discard any audio captured while Barnaby was speaking (avoids the
        robot mic picking up the robot speaker and replying to itself)."""
        while True:
            try:
                audio_q.get_nowait()
            except queue.Empty:
                break
        vad._buffer = []
        vad._in_speech = False

    console.print("[bold]Loading VAD + STT...[/bold]")
    vad = VADRecorder()
    stt = STTEngine()

    stop_event = external_stop if external_stop is not None else threading.Event()

    def shutdown(signum, frame):
        stop_event.set()

    if external_stop is None:
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    # Barnaby greets the user
    console.print("[bold magenta]Barnaby is waking up...[/bold magenta]")
    greeting = convo.greeting()
    _gesture(RobotState.READING_BACK)
    barnaby_tts.speak(greeting)
    _gesture(RobotState.IDLE)

    live_partial = ""

    mic_device = robot_audio.device_index()
    if mic_device is not None:
        console.print(f"[dim]Using robot audio device #{mic_device} ({robot_audio.AUDIO_DEVICE_NAME})[/dim]")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SAMPLES,
        callback=on_audio,
        device=mic_device,
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
                        state.status = "thinking"
                        _gesture(RobotState.PROCESSING)
                        live.update(render(state, "listening…"))
                        user_text = stt.transcribe(utterance)
                        if user_text:
                            live_partial = user_text
                            live.update(render(state, live_partial))
                            reply = convo.reply(user_text)
                            state.exchanges.append((user_text, reply))
                            live_partial = ""

                            state.status = "speaking"
                            _gesture(RobotState.READING_BACK)
                            live.update(render(state, ""))
                            barnaby_tts.speak(reply)
                            drain_mic()  # forget Barnaby's own voice
                            state.status = "idle"
                            _gesture(RobotState.IDLE)

                if state.status == "listening" and not vad._in_speech:
                    state.status = "idle"

                live.update(render(state, live_partial))

    console.print("\n[yellow]Barnaby is going back to his cozy barn...[/yellow]")
    path = save_transcript(state)
    if path:
        console.print(f"[green]Saved transcript:[/green] {path}")
    g = get_gestures()
    if g:
        g.stop()
    console.print("[bold magenta]🦇 Bye for now![/bold magenta]")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Barnaby the Bat")
    parser.add_argument("--robot", action="store_true", help="Enable Reachy Mini gestures")
    args = parser.parse_args()
    try:
        main(robot=args.robot)
    except KeyboardInterrupt:
        pass
    sys.exit(0)
