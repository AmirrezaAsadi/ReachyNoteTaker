# Phase 2 — Reachy Mini Integration

## Vision
Reachy Mini as a physical note-taking companion. You speak, it listens, reacts, and captures — like an attentive colleague sitting across from you. The robot's head motion gives you live, ambient feedback about which stage of the pipeline is running, so you never have to glance at the terminal to know whether you're being heard, transcribed, or written down.

## Robot Behavior States
Reachy Mini has distinct physical behaviors for each pipeline stage. `reachy_gestures.py` (Phase 2) defines and manages these states. Each state has consistent staging — same direction, same tempo every time — because consistency reads as personality, randomness reads as malfunction.

### State 1: IDLE (waiting for speech)
- Head slowly and gently sways side to side, very subtle
- Eyes dim slightly (if controllable)
- Neutral resting expression
- Behavior: "I'm here, ready when you are"

### State 2: LISTENING (VAD detected speech)
- Head orients and tilts slightly toward the speaker (attentive lean)
- Eyes brighten
- Very slight rhythmic nod in sync with speech energy/volume (louder speech = slightly more pronounced nod)
- Behavior: "I hear you, keep going"

### State 3: PROCESSING (STT + LLM cleaning the note)
- Head does a slow thoughtful tilt to one side
- Small repetitive micro-nod, like thinking/considering
- Slightly faster than idle sway but more purposeful
- Behavior: "I'm thinking about what you said"

### State 4: WRITING (LLM structuring, saving to file)
- Head bobs downward rhythmically, like looking down at a notepad
- Short quick nods, like pen strokes
- Speed of nodding matches estimated writing speed (longer note = more bobs)
- Behavior: "I'm writing this down"

### State 5: CONFIRMING (note saved, voice command accepted)
- Single confident slow nod downward then back up
- Brief pause, then returns to IDLE
- Behavior: "Got it, done"

### State 6: READING BACK (TTS speaking the note)
- Head moves gently with speech rhythm (TTS prosody-driven)
- Slight left-right scanning motion as if reading lines on a page
- Behavior: "Let me read that back to you"

### State 7: SUMMARIZING (end of session)
- Head lifts upward slightly (looking up, reflective)
- Slow gentle nodding while summary is being generated
- Then transitions to READING BACK for the spoken summary
- Behavior: "Let me think about everything we covered"

### State 8: ERROR / DIDN'T CATCH THAT
- Head tilts to one side with a slight confused lean
- Stays in that position briefly
- Short double-shake (not aggressive, more quizzical)
- Behavior: "Hmm, I didn't quite get that"

## Implementation Plan for `reachy_gestures.py`
- `set_state(state: RobotState)` — transitions robot to a behavior state
- `sync_to_audio_energy(energy_level: float)` — adjusts nod intensity to live microphone energy during LISTENING state
- `sync_to_note_length(word_count: int)` — controls bob count during WRITING state based on note length
- `sync_to_tts_prosody(phoneme_timestamps)` — drives head motion during READING BACK from TTS output timing
- All motions are non-blocking (run in background thread)
- Smooth transitions between states (no snapping)
- Motion parameters tunable via `.env`:
  - `GESTURE_INTENSITY=0.5` (0.0 = still, 1.0 = expressive)
  - `GESTURE_SPEED=1.0` (multiplier)
  - `GESTURE_ENABLED=true`

## What Changes in the Codebase for Phase 2
- `note_taker.py` gains a `--robot` flag that activates gesture sync
- `llm_processor.py` emits state change events the gesture system subscribes to
- `tts_reader.py` passes phoneme timing to gesture system during readback (hook already stubbed as `speak_phonemes_with_callback`)
- VAD energy level streamed to gesture system during LISTENING (already exposed as `VADRecorder.energy`)
- `reachy_gestures.py` wraps the Reachy Mini Python SDK
- `note_taker.py` becomes a WebSocket server, Reachy is the client
- Wake word added: "Hey Reachy, take a note"

## Gesture Tuning Notes
- WRITING state bob speed should feel like natural handwriting pace (~1 bob per 3–4 words estimated)
- LISTENING nod should never feel like aggressive agreement — keep it subtle, more like active listening than enthusiasm
- PROCESSING tilt should go to the same side every time (consistent = feels like personality, not random)
- All motions must stop cleanly if robot loses connection
- Never run two motion states simultaneously — queue them

## Estimated Effort per Component
| Component | Estimate |
| --- | --- |
| `reachy_gestures.py` core | ~2 days |
| VAD energy → nod sync | ~1 day |
| TTS prosody → head motion sync | ~2 days |
| State machine + transitions | ~1 day |
| Tuning and feel | ~2 days (most important part) |
| WebSocket server mode | ~1 day |
| Wake word integration | ~1 day |
| **Total** | **~10 days** |

## References
- Reachy Mini Python SDK: `pollen-robotics/reachy_mini_conversation_app`
- Reachy Mini joint control docs
- `huggingface/speech-to-speech` WebSocket server mode
