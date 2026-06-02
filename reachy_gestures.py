"""Reachy Mini gesture state machine for voice-notes pipeline.

Each pipeline stage maps to a named RobotState with a distinct head motion.
All motions run in a background thread; transitions are smooth and queued.
"""

from __future__ import annotations

import os
import threading
import time
from enum import Enum, auto
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

GESTURE_ENABLED = os.getenv("GESTURE_ENABLED", "true").lower() == "true"
GESTURE_INTENSITY = float(os.getenv("GESTURE_INTENSITY", "0.5"))
GESTURE_SPEED = float(os.getenv("GESTURE_SPEED", "1.0"))


class RobotState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    WRITING = auto()
    CONFIRMING = auto()
    READING_BACK = auto()
    SUMMARIZING = auto()
    ERROR = auto()


class ReachyGestures:
    """Manages Reachy Mini head gestures synchronized to pipeline state.

    Usage:
        gestures = ReachyGestures()
        gestures.start()
        gestures.set_state(RobotState.LISTENING)
        gestures.stop()
    """

    def __init__(self):
        self._state = RobotState.IDLE
        self._target_state = RobotState.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._state_changed = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._audio_energy = 0.0
        self._note_word_count = 0

        self._reachy = None
        self._connected = False
        self._connect()

    def _connect(self):
        if not GESTURE_ENABLED:
            return
        try:
            from reachy2_sdk import ReachySDK  # type: ignore

            self._reachy = ReachySDK(host="localhost")
            self._reachy.connect()
            self._connected = True
            print("[gestures] Reachy Mini connected.")
        except Exception as e:  # noqa: BLE001
            print(f"[gestures] Reachy not available: {e} — running in stub mode.")
            self._connected = False

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gestures")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._state_changed.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._connected and self._reachy:
            try:
                self._reachy.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def set_state(self, state: RobotState) -> None:
        with self._lock:
            self._target_state = state
        self._state_changed.set()

    def sync_to_audio_energy(self, energy_level: float) -> None:
        """Call during LISTENING with live mic RMS energy (0.0–1.0)."""
        self._audio_energy = max(0.0, min(1.0, energy_level * 10))

    def sync_to_note_length(self, word_count: int) -> None:
        """Call before WRITING to scale bob count to note length."""
        self._note_word_count = word_count

    def sync_to_tts_prosody(self, phoneme: str, t: float) -> None:
        """Phase 2: called per-phoneme during READING_BACK."""
        pass  # hook for prosody-driven head motion

    # --- internal motion loop ---

    def _loop(self):
        while not self._stop_event.is_set():
            self._state_changed.wait(timeout=0.1)
            self._state_changed.clear()

            with self._lock:
                if self._target_state != self._state:
                    self._transition_to(self._target_state)
                    self._state = self._target_state

            self._tick()

    def _transition_to(self, state: RobotState):
        """Smooth transition: return head to neutral before next motion."""
        self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=0.3)

    def _tick(self):
        """One motion cycle for the current state."""
        s = self._state
        i = GESTURE_INTENSITY
        sp = GESTURE_SPEED

        if s == RobotState.IDLE:
            self._sway(amplitude=0.03 * i, period=4.0 / sp)

        elif s == RobotState.LISTENING:
            nod_amp = 0.04 * i + 0.04 * i * self._audio_energy
            self._nod(amplitude=nod_amp, period=1.2 / sp)
            self._set_head(pan=0.1 * i, tilt=0.05 * i, roll=0.0, duration=0.3)

        elif s == RobotState.PROCESSING:
            self._set_head(roll=0.12 * i, tilt=0.0, pan=0.0, duration=0.6 / sp)
            self._micro_nod(count=3, amplitude=0.03 * i, period=0.4 / sp)

        elif s == RobotState.WRITING:
            bobs = max(2, self._note_word_count // 4)
            self._writing_bobs(count=bobs, amplitude=0.08 * i, period=0.5 / sp)

        elif s == RobotState.CONFIRMING:
            self._nod(amplitude=0.12 * i, period=0.8 / sp, count=1)
            time.sleep(0.4)
            self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=0.4)

        elif s == RobotState.READING_BACK:
            self._reading_scan(amplitude=0.06 * i, period=2.0 / sp)

        elif s == RobotState.SUMMARIZING:
            self._set_head(tilt=-0.08 * i, pan=0.0, roll=0.0, duration=0.8 / sp)
            self._micro_nod(count=4, amplitude=0.04 * i, period=0.5 / sp)

        elif s == RobotState.ERROR:
            self._set_head(roll=0.1 * i, tilt=0.0, pan=0.0, duration=0.4)
            time.sleep(0.5)
            self._shake(count=2, amplitude=0.06 * i, period=0.3 / sp)

    # --- low-level motion primitives ---

    def _set_head(self, tilt: float, pan: float, roll: float, duration: float):
        if not self._connected or not self._reachy:
            time.sleep(duration)
            return
        try:
            self._reachy.head.rotate_to(
                roll=roll, pitch=tilt, yaw=pan, duration=duration, degrees=False
            )
            time.sleep(duration + 0.05)
        except Exception:  # noqa: BLE001
            time.sleep(duration)

    def _sway(self, amplitude: float, period: float):
        self._set_head(tilt=0.0, pan=amplitude, roll=0.0, duration=period / 2)
        self._set_head(tilt=0.0, pan=-amplitude, roll=0.0, duration=period / 2)

    def _nod(self, amplitude: float, period: float, count: int = 1):
        for _ in range(count):
            self._set_head(tilt=amplitude, pan=0.0, roll=0.0, duration=period / 2)
            self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=period / 2)

    def _micro_nod(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            self._set_head(tilt=amplitude * 0.5, pan=0.0, roll=0.0, duration=period / 2)
            self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=period / 2)

    def _writing_bobs(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            if self._stop_event.is_set() or self._target_state != RobotState.WRITING:
                break
            self._set_head(tilt=amplitude, pan=0.0, roll=0.0, duration=period / 2)
            self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=period / 2)

    def _reading_scan(self, amplitude: float, period: float):
        self._set_head(tilt=0.0, pan=amplitude, roll=0.0, duration=period / 3)
        self._set_head(tilt=0.0, pan=-amplitude, roll=0.0, duration=period / 3)
        self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=period / 3)

    def _shake(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            self._set_head(tilt=0.0, pan=amplitude, roll=0.0, duration=period / 2)
            self._set_head(tilt=0.0, pan=-amplitude, roll=0.0, duration=period / 2)
        self._set_head(tilt=0.0, pan=0.0, roll=0.0, duration=0.3)


# Singleton used by note_taker.py when --robot is active
_instance: Optional[ReachyGestures] = None


def get_gestures() -> Optional[ReachyGestures]:
    return _instance


def init_gestures() -> ReachyGestures:
    global _instance
    _instance = ReachyGestures()
    _instance.start()
    return _instance
