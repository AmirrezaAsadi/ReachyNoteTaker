# voice-notes-local

Fully local, voice-powered note-taking for Apple Silicon Macs. Speak freely; a local LLM cleans, structures, and saves your notes as markdown.

## What it does

- Listens with **Silero VAD** — only transcribes when you're actually speaking
- Transcribes with **Parakeet-TDT 0.6B v3** via `parakeet-mlx` (Apple Silicon optimized)
- Cleans, structures, titles, and summarizes with **Gemma 4 E4B** served by `llama.cpp`
- Optional readback with **Qwen3-TTS 1.7B** via `mlx-audio`
- Glue: `huggingface/speech-to-speech`
- Notes saved as timestamped markdown in `~/voice-notes/`, organized by date with tags and a full-text search index
- Voice commands: new note, save, read back, summarize, tag, cancel
- 100% offline after setup

## Prerequisites

- Apple Silicon Mac (tested on M1 Max, 64GB)
- macOS 14+
- [Homebrew](https://brew.sh)
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (installed automatically by `setup.sh`)

## Install

```bash
git clone <this-repo> voice-notes-local
cd voice-notes-local
./setup.sh
```

`setup.sh` installs `llama.cpp` via Homebrew, creates a `.venv` with `uv`, installs Python deps, downloads the Gemma 4 E4B GGUF, and lays out `~/voice-notes/`.

## Quick start

```bash
cp .env.example .env
./run.sh
```

`run.sh` starts `llama-server` in the background, waits for its health check, and launches the live note-taking UI. `Ctrl+C` cleanly shuts everything down and saves any open note.

## Voice commands

Speak these naturally; they're matched before the segment is sent to the note LLM.

| Command           | What it does                                    | Example                          |
| ----------------- | ----------------------------------------------- | -------------------------------- |
| `new note`        | Saves current note (if any) and starts a fresh one | "Okay, new note."             |
| `save note`       | Saves the current note immediately              | "Save note."                     |
| `read back`       | TTS reads the current note aloud                | "Read back."                     |
| `summarize`       | LLM generates a session summary                 | "Summarize."                     |
| `add tag <name>`  | Tags the current note                           | "Add tag work."                  |
| `cancel`          | Discards the current unsaved note               | "Cancel."                        |

## Searching notes

```bash
./search.sh "meeting"          # full-text search
./search.sh --tag work         # filter by tag
./search.sh --date 2026-06-02  # filter by date
./search.sh --today            # today's notes
```

## Custom TTS voice

Clone your own voice from a 5–15 second `.wav`:

```bash
./clone_voice.sh my_voice.wav
```

The preset is saved to `~/.voice-notes-voice.qvp` and picked up automatically by `tts_reader.py`. Override with `TTS_VOICE_PRESET` in `.env`. Disable TTS entirely with `TTS_ENABLED=false`.

## Note layout

```
~/voice-notes/
├── 2026-06-02/
│   ├── note-001-meeting-recap.md
│   ├── note-002-ideas.md
│   └── session-summary.md
├── tags/
│   └── index.json
└── search-index.json
```

Each note has frontmatter:

```yaml
---
title: Meeting recap
date: 2026-06-02T10:14:33
tags: [work, planning]
summary: Discussed Q3 roadmap and shipping dates.
duration: 184
word_count: 312
---
```

## Phase 2 — Reachy Mini integration (coming soon)

The next phase turns this into a physical note-taking companion using the [Reachy Mini](https://www.pollen-robotics.com/reachy/) robot. The robot will:

- Sit always-on across from you, listening passively
- React physically to each pipeline stage — attentive lean while listening, thoughtful tilt while processing, downward bobs like a pen on paper while writing, a confident nod when a note is saved
- Speak summaries aloud at the end of each session with synchronized head motion
- Wake on "Hey Reachy, take a note"

See [PHASE2_ROADMAP.md](PHASE2_ROADMAP.md) for the full behavior state machine, gesture tuning notes, and implementation plan.

## Troubleshooting

**`llama-server` won't start** — check `brew list llama.cpp`; reinstall with `brew reinstall llama.cpp`. Confirm the GGUF path in `.env` exists.

**No audio captured** — System Settings → Privacy & Security → Microphone → enable for your terminal. Verify with `python -c "import sounddevice; print(sounddevice.query_devices())"`.

**Parakeet/MLX errors on first run** — model weights download on first use; ensure network access on first launch, then it's fully offline.

**TTS sounds robotic / wrong voice** — re-run `./clone_voice.sh` with a cleaner 10s sample (quiet room, no music).

**High latency** — drop `LLM_CONTEXT_SIZE` in `.env` to 4096; close other MLX/Metal workloads.

**Notes not saving** — check `~/voice-notes/` permissions and `NOTES_DIR` in `.env`.

**Voice command not detected** — speak it as a complete short utterance with a pause before and after. Check `LOG_LEVEL=DEBUG` to see what the command detector saw.
