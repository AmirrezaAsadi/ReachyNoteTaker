#!/usr/bin/env bash
set -euo pipefail

# Load .env
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

LLM_MODEL_PATH="${LLM_MODEL_PATH/#\~/$HOME}"
SERVER_PORT="${SERVER_PORT:-8080}"
LLM_CONTEXT_SIZE="${LLM_CONTEXT_SIZE:-8192}"

if [ ! -f "$LLM_MODEL_PATH" ]; then
  echo "Model not found at $LLM_MODEL_PATH — run ./setup.sh first." >&2
  exit 1
fi

# Activate venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Starting llama-server on :$SERVER_PORT"
llama-server \
  -m "$LLM_MODEL_PATH" \
  -c "$LLM_CONTEXT_SIZE" \
  --port "$SERVER_PORT" \
  --host 127.0.0.1 \
  -ngl 99 \
  --log-disable \
  > /tmp/voice-notes-llama.log 2>&1 &

LLAMA_PID=$!

cleanup() {
  echo
  echo "==> Shutting down..."
  # Tell the note app to save first
  kill -INT "$NOTE_PID" 2>/dev/null || true
  wait "$NOTE_PID" 2>/dev/null || true
  kill "$LLAMA_PID" 2>/dev/null || true
  wait "$LLAMA_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup INT TERM EXIT

echo "==> Waiting for llama-server health..."
for i in {1..60}; do
  if curl -sf "http://127.0.0.1:$SERVER_PORT/health" >/dev/null 2>&1; then
    echo "==> llama-server ready."
    break
  fi
  if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
    echo "llama-server died — see /tmp/voice-notes-llama.log" >&2
    exit 1
  fi
  sleep 1
done

echo "==> Launching note taker..."
python note_taker.py &
NOTE_PID=$!
wait "$NOTE_PID"
