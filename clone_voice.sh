#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <sample.wav>  (5-15 seconds, mono, clean speech)" >&2
  exit 1
fi

SAMPLE="$1"
if [ ! -f "$SAMPLE" ]; then
  echo "File not found: $SAMPLE" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python - "$SAMPLE" <<'PY'
import sys
from pathlib import Path
import soundfile as sf

sample = Path(sys.argv[1]).resolve()
data, sr = sf.read(str(sample))
duration = len(data) / sr
if duration < 4:
    print(f"Sample is {duration:.1f}s — ideally 5-15s for best quality (proceeding anyway).")
elif duration > 15:
    print(f"Sample is {duration:.1f}s — trim to under 15s for best results.", file=sys.stderr)
    sys.exit(2)

# Test that voice cloning works with this file
print(f"Testing voice clone with {sample.name} ({duration:.1f}s)...")
from mlx_audio.tts.generate import generate_audio
import tempfile, os

with tempfile.TemporaryDirectory() as td:
    generate_audio(
        text="Hello, this is a voice test.",
        model="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
        ref_audio=str(sample),
        play=False,
        verbose=False,
        save=False,
        output_path=td,
    )

# Save path as preset — generate_audio uses ref_audio at runtime
out = Path.home() / ".voice-notes-voice.wav"
import shutil
shutil.copy(str(sample), str(out))
print(f"Voice preset saved to {out}")
print("Update TTS_VOICE_PRESET in .env to point at this file if needed.")
PY
