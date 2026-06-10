#!/usr/bin/env bash
# Install mcp-coder globally — one command, works from any directory after.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
LINK="/usr/local/bin/mcp-coder"

# 1. Build the venv if it doesn't exist yet (no sudo — user-owned)
if [[ ! -x "$REPO/.venv/bin/python" ]]; then
  echo "==> Creating venv..."
  python3 -m venv "$REPO/.venv"
  "$REPO/.venv/bin/pip" install -q -U pip wheel
  "$REPO/.venv/bin/pip" install -q -e "$REPO"
  echo "    venv ready."
fi

# 2. Write a tiny wrapper to /usr/local/bin (may need sudo)
# Remove any old symlink first so we don't write through it into the repo.
_write_wrapper() {
  rm -f "$LINK"
  cat > "$LINK" <<EOF
#!/usr/bin/env bash
exec "$REPO/scripts/mcp-coder" "\$@"
EOF
  chmod +x "$LINK"
}

if [[ -w "$(dirname "$LINK")" ]]; then
  _write_wrapper
else
  echo "==> /usr/local/bin is not writable — using sudo for this step only..."
  sudo bash -c "$(declare -f _write_wrapper); LINK='$LINK'; REPO='$REPO'; _write_wrapper"
fi

echo ""
echo "✓  mcp-coder installed → $LINK"
echo "   (uses $REPO/.env for keys; venv at $REPO/.venv)"
echo ""
echo "Try it:"
echo "   mcp-coder setup"
