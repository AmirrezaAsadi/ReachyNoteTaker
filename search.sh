#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true
exec python -m _search_cli "$@"
