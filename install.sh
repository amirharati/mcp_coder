#!/usr/bin/env bash
# One-time global install: editable venv + symlink to live repo scripts.
# After this, code edits in the repo are picked up on MCP restart — no reinstall.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
LINK="/usr/local/bin/mcp-coder"
VENV_PY="$REPO/.venv/bin/python"
VENV_PIP="$REPO/.venv/bin/pip"

# 1. Create venv if missing
if [[ ! -x "$VENV_PY" ]]; then
  echo "==> Creating venv..."
  python3 -m venv "$REPO/.venv"
  "$VENV_PIP" install -q -U pip wheel
  echo "    venv ready."
fi

# 2. Always refresh editable install (idempotent — picks up pyproject changes too)
echo "==> Linking editable install from $REPO"
"$VENV_PIP" install -q -e "$REPO"

# 3. Symlink scripts/mcp-coder → /usr/local/bin/mcp-coder (live path, not a copy)
_link_binary() {
  rm -f "$LINK"
  ln -sf "$REPO/scripts/mcp-coder" "$LINK"
}

if [[ -w "$(dirname "$LINK")" ]]; then
  _link_binary
else
  echo "==> /usr/local/bin is not writable — using sudo for this step only..."
  sudo bash -c "$(declare -f _link_binary); LINK='$LINK'; REPO='$REPO'; _link_binary"
fi

echo ""
echo "✓  mcp-coder installed → $LINK"
echo "   source:  $REPO  (editable — edits apply on MCP restart)"
echo "   venv:    $REPO/.venv"
echo "   env:     $REPO/.env  (or MCP_CODER_ENV_FILE in mcp.json)"
echo ""
echo "Dev workflow:"
echo "   1. Edit code in $REPO"
echo "   2. Restart MCP in Cursor (Settings → MCP) or: make mcp-kill"
echo "   No reinstall needed."
echo ""
echo "Wire Cursor:"
echo "   mcp-coder setup --local    # this project only"
echo "   mcp-coder setup --global   # all projects"
