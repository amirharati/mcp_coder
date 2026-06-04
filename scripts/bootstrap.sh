#!/usr/bin/env bash
# Create venv and install mcp-coder.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3.12}"
LOCKED=0
DEV=0

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap.sh [options]

Options:
  --locked    Install from requirements-lock.txt (reproducible; recommended for CI)
  --dev       Also install pytest (dev extras or requirements-dev.txt)
  -h, --help  Show this help

Environment:
  PYTHON      Python executable for venv (default: python3.12)

Examples:
  ./scripts/bootstrap.sh --locked          # reproducible runtime install
  ./scripts/bootstrap.sh --locked --dev    # locked + pytest
  ./scripts/bootstrap.sh                   # editable install from pyproject ranges
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --locked) LOCKED=1 ;;
    --dev) DEV=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found" >&2
  exit 1
fi

"$PYTHON" -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install -U pip wheel

if [[ "$LOCKED" -eq 1 ]]; then
  if [[ "$DEV" -eq 1 ]]; then
    pip install -r requirements-dev.txt
  else
    pip install -r requirements-lock.txt
  fi
  pip install -e . --no-deps
else
  if [[ "$DEV" -eq 1 ]]; then
    pip install -e ".[dev]"
  else
    pip install -e .
  fi
fi

echo ""
echo "Installed mcp-coder into .venv"
python -c "import mcp; from aider.coders import Coder; print('mcp:', mcp.__version__ if hasattr(mcp,'__version__') else 'ok', '| aider: ok')"
echo "Run MCP server: .venv/bin/python main.py --mcp"
echo "Run tests:       .venv/bin/pytest"
