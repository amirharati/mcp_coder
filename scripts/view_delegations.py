#!/usr/bin/env python3
"""Serve a small UI to review delegations.jsonl. Opens your browser.

Backward-compat wrapper — prefer: mcp-coder view delegations
"""

from __future__ import annotations

import sys

from core.cli.view_delegations import main_view

if __name__ == "__main__":
    raise SystemExit(main_view(sys.argv[1:]))
