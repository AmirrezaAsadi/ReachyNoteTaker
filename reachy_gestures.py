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
# Wing-beat (antennas) amplitude in degrees at full intensity. Kept gentle.
WING_AMP_DEG = float(os.getenv("GESTURE_WING_AMP", "16"))
# Antennas move in opposite directions (one up, one down) like a bird's wings.
# Flip to "-1" if your antennas are mirror-mounted and the beat looks inverted.
WING_SIGN = float(os.getenv("GESTURE_WING_SIGN", "1"))

# Safety limits (degrees): pitch/roll ±40, yaw ±180
_PITCH_LIMIT = 35.0
_ROLL_LIMIT = 35.0
_YAW_LIMIT = 60.0  # conservative for gestures
_CONTROL_HZ = 50.0  # set_target update rate for smooth continuous motion


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

    def __init__(self, _reachy=None):
        self._state = RobotState.IDLE
        self._target_state = RobotState.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._state_changed = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._audio_energy = 0.0
        self._note_word_count = 0

        if _reachy is not None:
            # Reuse an already-connected instance (e.g. passed by ReachyMiniApp)
            self._reachy = _reachy
            self._connected = True
            print("[gestures] Using existing Reachy Mini connection.")
        else:
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
                self._reachy.goto_target(head=NEUTRAL, antennas=[0.0, 0.0], duration=1.0, body_yaw=None)
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

    # --- continuous motion loop (set_target @ ~50Hz) ---

    def _loop(self):
        """Drive head + antennas continuously as smooth functions of time.

        A single command stream (set_target) avoids head/antenna conflicts and
        keeps the bat's wings flapping the whole time it's awake.
        """
        dt = 1.0 / _CONTROL_HZ
        state_t0 = time.time()
        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                target = self._target_state
            if target != self._state:
                self._state = target
                state_t0 = now  # reset phase so each state starts cleanly

            t = now - state_t0
            head, antennas = self._compute(self._state, t)
            self._send(head, antennas)
            time.sleep(dt)

    def _wings(self, t: float, beat_hz: float, amp_deg: float) -> list[float]:
        """Antennas beat in opposite directions like a bird's wings in flight."""
        a = np.deg2rad(amp_deg * GESTURE_INTENSITY * np.sin(2 * np.pi * beat_hz * GESTURE_SPEED * t))
        return [WING_SIGN * a, -WING_SIGN * a]

    def _compute(self, state: RobotState, t: float):
        """Return (head 4x4 pose, [right_rad, left_rad]) for this instant."""
        i = GESTURE_INTENSITY
        sp = GESTURE_SPEED
        s = lambda hz: np.sin(2 * np.pi * hz * sp * t)

        if state == RobotState.IDLE:
            head = _head_pose(yaw_deg=3.0 * i * s(0.12))
            wings = self._wings(t, beat_hz=0.7, amp_deg=0.4 * WING_AMP_DEG)

        elif state == RobotState.LISTENING:
            nod = (3.0 * i + 4.0 * i * self._audio_energy) * s(1.0)
            head = _head_pose(yaw_deg=8.0 * i, pitch_deg=4.0 * i + nod)
            wings = self._wings(t, beat_hz=1.0, amp_deg=0.5 * WING_AMP_DEG)

        elif state == RobotState.PROCESSING:
            head = _head_pose(roll_deg=12.0 * i, pitch_deg=2.0 * i * s(1.5))
            wings = self._wings(t, beat_hz=0.6, amp_deg=0.35 * WING_AMP_DEG)

        elif state == RobotState.WRITING:
            head = _head_pose(pitch_deg=8.0 * i * abs(s(1.0)))
            wings = self._wings(t, beat_hz=1.2, amp_deg=0.55 * WING_AMP_DEG)

        elif state == RobotState.CONFIRMING:
            head = _head_pose(pitch_deg=12.0 * i * s(1.2))
            wings = self._wings(t, beat_hz=1.3, amp_deg=0.6 * WING_AMP_DEG)

        elif state == RobotState.READING_BACK:
            # Speaking: gentle scan + bob, wings gliding (calm, never frantic)
            head = _head_pose(yaw_deg=6.0 * i * s(0.4), pitch_deg=3.0 * i * s(0.8))
            wings = self._wings(t, beat_hz=1.4, amp_deg=0.85 * WING_AMP_DEG)

        elif state == RobotState.SUMMARIZING:
            head = _head_pose(pitch_deg=-8.0 * i + 3.0 * i * s(0.6))
            wings = self._wings(t, beat_hz=0.9, amp_deg=0.45 * WING_AMP_DEG)

        elif state == RobotState.ERROR:
            head = _head_pose(roll_deg=10.0 * i, yaw_deg=6.0 * i * s(3.0))
            wings = [0.0, 0.0]  # wings still — quizzical pause

        else:
            head = NEUTRAL
            wings = [0.0, 0.0]

        return head, wings

    def _send(self, head: np.ndarray, antennas: list[float]):
        if not self._connected or not self._reachy:
            return
        try:
            self._reachy.set_target(head=head, antennas=antennas)
        except Exception:  # noqa: BLE001
            pass


# Module-level singleton used by note_taker.py --robot
_instance: Optional[ReachyGestures] = None


def get_gestures() -> Optional[ReachyGestures]:
    return _instance


def init_gestures() -> ReachyGestures:
    global _instance
    _instance = ReachyGestures()
    _instance.start()
    return _instance
