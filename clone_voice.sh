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

sample = Path(sys.argv[1])
data, sr = sf.read(str(sample))
duration = len(data) / sr
if duration < 5 or duration > 15:
    print(f"Sample is {duration:.1f}s — must be 5–15s.", file=sys.stderr)
    sys.exit(2)

out = Path.home() / ".voice-notes-voice.qvp"
try:
    from mlx_audio.tts import Qwen3TTS
    tts = Qwen3TTS(model="Qwen/Qwen3-TTS-1.7B")
    tts.clone_voice(str(sample), output_path=str(out))
except Exception as e:
    print(f"Voice cloning failed: {e}", file=sys.stderr)
    sys.exit(3)

print(f"Saved voice preset to {out}")
PY
