from __future__ import annotations

import os
from pathlib import Path


def load_env_files() -> list[Path]:
    """
    Load environment variables from .env files (optional).

    Order (first existing file wins for each variable; later files do not override
    variables already set in the environment):
      1. MCP_CODER_ENV_FILE — explicit path
      2. .env in process cwd (Cursor MCP `cwd` is usually the target workspace)
      3. .env in the mcp-coder repo root (next to pyproject.toml)

    Does nothing if python-dotenv is unavailable. Never required for install/tests.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []

    loaded: list[Path] = []
    candidates: list[Path] = []

    explicit = os.environ.get("MCP_CODER_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())

    candidates.append(Path.cwd() / ".env")

    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / ".env")

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        load_dotenv(path, override=False)
        loaded.append(resolved)

    return loaded
