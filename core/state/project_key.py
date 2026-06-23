from __future__ import annotations

import os
import re
from pathlib import Path


class ProjectKeyResolver:
    @staticmethod
    def from_spec_path(spec_path: str | None) -> str:
        """Derive project key from spec_path with optional env override."""
        env_override = os.environ.get("MCP_CODER_PROJECT_KEY")
        if env_override is not None and env_override.strip():
            return env_override.strip()

        if spec_path is None:
            return "default"

        normalized = str(spec_path).strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = normalized.strip("/")
        if not normalized:
            return "default"

        parts = [segment for segment in normalized.split("/") if segment and segment != "."]
        if parts[:2] == [".mcp-coder", "specs"]:
            parts = parts[2:]
        if not parts:
            return "default"

        if len(parts) == 1:
            return ProjectKeyResolver._leaf_key(parts[0])

        first = parts[0]
        second = parts[1]
        if len(parts) == 2:
            second = ProjectKeyResolver._leaf_key(second)
        return f"{first}/{second}" if second else first

    @staticmethod
    def _leaf_key(segment: str) -> str:
        stem = Path(segment).stem.strip()
        if not stem:
            stem = segment.strip()
        stem = re.sub(r"-\d+(?:-.+)?$", "", stem)
        return stem or "default"
