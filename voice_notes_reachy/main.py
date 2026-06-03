"""VoiceNotesReachy — Reachy Mini app entry point.

The framework calls run(reachy_mini, stop_event); we start the full
note-taking pipeline (VAD → STT → LLM → save) and pass the live
ReachyMini instance to the gesture system so it can sync head motion
to each pipeline stage.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

# Allow imports from the repo root (note_store, llm_processor, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent))

from reachy_mini import ReachyMini, ReachyMiniApp

import reachy_gestures as gestures
from reachy_gestures import RobotState


class VoiceNotesReachy(ReachyMiniApp):
    custom_app_url = None       # no web UI needed — we use the Rich terminal
    dont_start_webserver = True
    request_media_backend = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        # Hand the live robot instance to the gesture system
        gestures._instance = gestures.ReachyGestures(_reachy=reachy_mini)
        gestures._instance.start()

        try:
            # Import here so heavy deps load inside the app's venv context
            from note_taker import main as run_notes
            run_notes(robot=True, external_stop=stop_event)
        finally:
            if gestures._instance:
                gestures._instance.stop()


if __name__ == "__main__":
    app = VoiceNotesReachy()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
