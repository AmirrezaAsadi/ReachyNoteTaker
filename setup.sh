#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}==>${NC} $1"; }
warn()  { echo -e "${YELLOW}!! ${NC} $1"; }
fail()  { echo -e "${RED}xx${NC} $1"; exit 1; }

# --- Homebrew ---
if ! command -v brew >/dev/null 2>&1; then
  info "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  info "Homebrew found."
fi

# --- llama.cpp ---
if ! command -v llama-server >/dev/null 2>&1; then
  info "Installing llama.cpp..."
  brew install llama.cpp
else
  info "llama.cpp found."
fi

# --- uv ---
if ! command -v uv >/dev/null 2>&1; then
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  info "uv found."
fi

# --- Python venv ---
info "Creating Python 3.11 virtual environment..."
uv venv --python 3.11 .venv
# shellcheck disable=SC1091
source .venv/bin/activate

info "Installing Python dependencies..."
uv pip install -r requirements.txt

# --- Gemma model ---
MODEL_DIR="$HOME/.cache/voice-notes"
MODEL_FILE="$MODEL_DIR/gemma-4-E4B-it-Q4_K_M.gguf"
mkdir -p "$MODEL_DIR"

if [ ! -f "$MODEL_FILE" ]; then
  info "Downloading Gemma 4 E4B GGUF (this may take a while)..."
  uv run huggingface-cli download \
    unsloth/gemma-4-E4B-it-GGUF \
    --include "gemma-4-E4B-it-Q4_K_M.gguf" \
    --local-dir "$MODEL_DIR" \
    || warn "Model download failed — fetch manually and point LLM_MODEL_PATH at it."
else
  info "Gemma model already present."
fi

# --- Notes directory ---
NOTES_DIR="${NOTES_DIR:-$HOME/voice-notes}"
info "Creating note storage at $NOTES_DIR..."
mkdir -p "$NOTES_DIR/tags"
[ -f "$NOTES_DIR/tags/index.json" ] || echo '{}' > "$NOTES_DIR/tags/index.json"
[ -f "$NOTES_DIR/search-index.json" ] || echo '{}' > "$NOTES_DIR/search-index.json"

# --- .env ---
if [ ! -f .env ]; then
  cp .env.example .env
  info "Created .env from .env.example."
fi

chmod +x run.sh search.sh clone_voice.sh 2>/dev/null || true

echo
info "Setup complete!"
cat <<EOF

Quick start:
  ./run.sh                 # start a note-taking session
  ./search.sh "keyword"    # search your notes
  ./clone_voice.sh me.wav  # clone your voice for TTS

Edit .env to tweak ports, paths, and behavior.
EOF
