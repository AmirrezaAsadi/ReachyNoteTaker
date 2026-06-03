---
title: Barnaby the Bat
emoji: 🦇
colorFrom: purple
colorTo: gray
sdk: static
pinned: false
short_description: A friendly Big Brown Bat conversation companion for Reachy Mini
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# 🦇 Barnaby the Bat

A friendly, fully-local conversation companion for **Reachy Mini**. Barnaby is a gentle Big Brown Bat from Cincinnati who loves chatting, reassuring nervous humans that bats are kind neighbors, and sharing fun bat facts — all in his own cloned voice, with the robot reacting physically as he listens and speaks.

## What it does

- **Listens** with Silero VAD + Parakeet-TDT STT (Apple Silicon, fully local)
- **Roleplays** as Barnaby via a local Gemma model (`llama.cpp`), staying in character
- **Speaks** in Barnaby's cloned voice (`barnaby.wav`) via Qwen3-TTS, with a signature bat sound effect (`StartingVoice-Ending.wav`) before and after each reply
- **Reacts** physically — Reachy Mini leans in while listening, tilts thoughtfully while thinking, and bobs gently while speaking
- **Saves** every conversation as a dated markdown transcript in `~/voice-notes/barnaby/`

## Run it

With the robot:

```bash
./run.sh                       # starts llama-server
python barnaby_app.py --robot  # or: python -m barnaby_bat.main
```

Without the robot (voice only):

```bash
./run.sh
python barnaby_app.py
```

Talk naturally; Barnaby replies whenever you pause. `Ctrl+C` says goodbye and saves the transcript.

## Assets

| File | Purpose |
| --- | --- |
| `assets/Barnaby_Bat_Profile.md` | Character profile fed into the system prompt |
| `assets/barnaby.wav` | Voice reference for TTS cloning |
| `assets/StartingVoice-Ending.wav` | Sound effect played before/after each reply |

## Configuration

`.env` knobs (copy from `.env.example`): `TTS_ENABLED`, `LLM_MODEL_PATH`, `NOTES_DIR`, `SERVER_PORT`, plus the gesture tuning vars `GESTURE_ENABLED`, `GESTURE_INTENSITY`, `GESTURE_SPEED`.

Built on the same local pipeline as [voice-notes-local](https://github.com/AmirrezaAsadi/ReachyNoteTaker); this is the conversation-companion sibling.
