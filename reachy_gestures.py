"""Reachy Mini gesture state machine for voice-notes pipeline.

Each pipeline stage maps to a named RobotState with a distinct head motion.
All motions run in a background thread; transitions are smooth and queued.

SDK: reachy_mini (ReachyMini), head controlled via 4x4 pose matrices.
Uses goto_target() for all smooth gestures (blocks caller thread, so we
run everything inside our own daemon thread).
"""

from __future__ import annotations

import os
import threading
import time
from enum import Enum, auto
from typing import Optional

import numpy as np
from dotenv import load_dotenv

load_dotenv()

GESTURE_ENABLED = os.getenv("GESTURE_ENABLED", "true").lower() == "true"
GESTURE_INTENSITY = float(os.getenv("GESTURE_INTENSITY", "0.5"))
GESTURE_SPEED = float(os.getenv("GESTURE_SPEED", "1.0"))

# Safety limits (degrees): pitch/roll ±40, yaw ±180
_PITCH_LIMIT = 35.0
_ROLL_LIMIT = 35.0
_YAW_LIMIT = 60.0  # conservative for gestures


class RobotState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    WRITING = auto()
    CONFIRMING = auto()
    READING_BACK = auto()
    SUMMARIZING = auto()
    ERROR = auto()


def _head_pose(roll_deg: float = 0.0, pitch_deg: float = 0.0, yaw_deg: float = 0.0) -> np.ndarray:
    """Build a 4x4 head pose matrix from roll/pitch/yaw in degrees via SDK utility."""
    from reachy_mini.utils import create_head_pose

    return create_head_pose(
        roll=float(np.clip(roll_deg, -_ROLL_LIMIT, _ROLL_LIMIT)),
        pitch=float(np.clip(pitch_deg, -_PITCH_LIMIT, _PITCH_LIMIT)),
        yaw=float(np.clip(yaw_deg, -_YAW_LIMIT, _YAW_LIMIT)),
        degrees=True,
    )


NEUTRAL = _head_pose()


class ReachyGestures:
    """Manages Reachy Mini head gestures synchronized to pipeline state.

    Usage:
        gestures = ReachyGestures()
        gestures.start()
        gestures.set_state(RobotState.LISTENING)
        ...
        gestures.stop()
    """

    def __init__(self):
        self._state = RobotState.IDLE
        self._target_state = RobotState.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._state_changed = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._audio_energy = 0.0   # 0.0–1.0, updated during LISTENING
        self._note_word_count = 0

        self._reachy = None
        self._connected = False
        self._connect()

    def _connect(self):
        if not GESTURE_ENABLED:
            return
        try:
            from reachy_mini import ReachyMini  # type: ignore

            self._reachy = ReachyMini(media_backend="no_media")
            self._connected = True
            print("[gestures] Reachy Mini connected.")
        except Exception as e:  # noqa: BLE001
            print(f"[gestures] Reachy not available: {e} — stub mode.")
            self._connected = False

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gestures")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._state_changed.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._connected and self._reachy:
            try:
                self._goto(NEUTRAL, duration=1.0)
            except Exception:  # noqa: BLE001
                pass

    def set_state(self, state: RobotState) -> None:
        with self._lock:
            self._target_state = state
        self._state_changed.set()

    def sync_to_audio_energy(self, energy_level: float) -> None:
        """Feed live mic RMS energy (0.0–1.0) during LISTENING for nod scaling."""
        self._audio_energy = max(0.0, min(1.0, energy_level * 10))

    def sync_to_note_length(self, word_count: int) -> None:
        """Set before WRITING to scale bob count to note length."""
        self._note_word_count = word_count

    def sync_to_tts_prosody(self, phoneme: str, t: float) -> None:
        """Phase 2 hook — called per-phoneme during READING_BACK."""
        pass

    # --- internal motion loop ---

    def _loop(self):
        while not self._stop_event.is_set():
            self._state_changed.wait(timeout=0.15)
            self._state_changed.clear()
            if self._stop_event.is_set():
                break

            with self._lock:
                new_state = self._target_state

            if new_state != self._state:
                self._goto(NEUTRAL, duration=0.4 / GESTURE_SPEED)
                self._state = new_state

            self._tick()

    def _tick(self):
        """One motion cycle for the current state."""
        i = GESTURE_INTENSITY
        sp = GESTURE_SPEED

        if self._state == RobotState.IDLE:
            self._sway(amplitude=3.0 * i, period=4.0 / sp)

        elif self._state == RobotState.LISTENING:
            nod_amp = 3.0 * i + 4.0 * i * self._audio_energy
            self._nod(amplitude=nod_amp, period=1.2 / sp)
            self._goto(_head_pose(yaw_deg=8.0 * i, pitch_deg=4.0 * i), duration=0.3)

        elif self._state == RobotState.PROCESSING:
            # Consistent right-side tilt every time (same side = personality)
            self._goto(_head_pose(roll_deg=12.0 * i), duration=0.6 / sp)
            self._micro_nod(count=3, amplitude=3.0 * i, period=0.4 / sp)

        elif self._state == RobotState.WRITING:
            bobs = max(2, self._note_word_count // 4)
            self._writing_bobs(count=bobs, amplitude=8.0 * i, period=0.5 / sp)

        elif self._state == RobotState.CONFIRMING:
            self._nod(amplitude=12.0 * i, period=0.8 / sp, count=1)
            self._goto(NEUTRAL, duration=0.4)

        elif self._state == RobotState.READING_BACK:
            self._reading_scan(amplitude=6.0 * i, period=2.0 / sp)

        elif self._state == RobotState.SUMMARIZING:
            # Head lifts upward — looking up, reflective
            self._goto(_head_pose(pitch_deg=-8.0 * i), duration=0.8 / sp)
            self._micro_nod(count=4, amplitude=4.0 * i, period=0.5 / sp)

        elif self._state == RobotState.ERROR:
            self._goto(_head_pose(roll_deg=10.0 * i), duration=0.4)
            time.sleep(0.5)
            self._shake(count=2, amplitude=6.0 * i, period=0.3 / sp)
            self._goto(NEUTRAL, duration=0.3)

    # --- low-level motion primitives (all blocking, run in gesture thread) ---

    def _goto(self, pose: np.ndarray, duration: float):
        duration = max(0.5, duration)  # SDK minimum
        if not self._connected or not self._reachy:
            time.sleep(duration)
            return
        if self._stop_event.is_set():
            return
        try:
            self._reachy.goto_target(head=pose, duration=duration, body_yaw=None)
        except Exception:  # noqa: BLE001
            time.sleep(duration)

    def _sway(self, amplitude: float, period: float):
        self._goto(_head_pose(yaw_deg=amplitude), duration=period / 2)
        self._goto(_head_pose(yaw_deg=-amplitude), duration=period / 2)
        self._goto(NEUTRAL, duration=period / 4)

    def _nod(self, amplitude: float, period: float, count: int = 1):
        for _ in range(count):
            self._goto(_head_pose(pitch_deg=amplitude), duration=period / 2)
            self._goto(NEUTRAL, duration=period / 2)

    def _micro_nod(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            self._goto(_head_pose(pitch_deg=amplitude * 0.5), duration=period / 2)
            self._goto(NEUTRAL, duration=period / 2)

    def _writing_bobs(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            if self._stop_event.is_set() or self._target_state != RobotState.WRITING:
                break
            self._goto(_head_pose(pitch_deg=amplitude), duration=period / 2)
            self._goto(NEUTRAL, duration=period / 2)

    def _reading_scan(self, amplitude: float, period: float):
        self._goto(_head_pose(yaw_deg=amplitude), duration=period / 3)
        self._goto(_head_pose(yaw_deg=-amplitude), duration=period / 3)
        self._goto(NEUTRAL, duration=period / 3)

    def _shake(self, count: int, amplitude: float, period: float):
        for _ in range(count):
            self._goto(_head_pose(yaw_deg=amplitude), duration=period / 2)
            self._goto(_head_pose(yaw_deg=-amplitude), duration=period / 2)
        self._goto(NEUTRAL, duration=0.3)


# Module-level singleton used by note_taker.py --robot
_instance: Optional[ReachyGestures] = None


def get_gestures() -> Optional[ReachyGestures]:
    return _instance


def init_gestures() -> ReachyGestures:
    global _instance
    _instance = ReachyGestures()
    _instance.start()
    return _instance
