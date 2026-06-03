"""BarnabyBat — Reachy Mini app entry point.

The framework calls run(reachy_mini, stop_event); we start the Barnaby
conversation loop and hand the live ReachyMini instance to the gesture
system so head motion syncs to each stage (listening, thinking, speaking).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

# Allow imports from the repo root (barnaby_app, reachy_gestures, ...)
sys.path.insert(0, str(Path(__file__).parent.parent))

from reachy_mini import ReachyMini, ReachyMiniApp

import reachy_gestures as gestures


class BarnabyBat(ReachyMiniApp):
    custom_app_url = None
    dont_start_webserver = True
    request_media_backend = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        gestures._instance = gestures.ReachyGestures(_reachy=reachy_mini)
        gestures._instance.start()
        try:
            from barnaby_app import main as run_chat
            run_chat(robot=True, external_stop=stop_event)
        finally:
            if gestures._instance:
                gestures._instance.stop()


if __name__ == "__main__":
    app = BarnabyBat()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
