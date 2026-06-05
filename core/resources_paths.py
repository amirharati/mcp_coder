"""Paths to repo-root resources/ (consumer bundles — not .cursor/rules/ for this package)."""

from __future__ import annotations

from pathlib import Path

RESOURCES_DIRNAME = "resources"


def repo_root() -> Path:
    """mcp-coder package root (contains resources/ and main.py)."""
    probe = Path(__file__).resolve()
    for parent in probe.parents:
        res = parent / RESOURCES_DIRNAME
        if res.is_dir() and (res / "spec-template.md").is_file():
            return parent
        if (parent / "main.py").is_file() and (parent / "pyproject.toml").is_file():
            if (parent / RESOURCES_DIRNAME).is_dir():
                return parent
    raise FileNotFoundError(f"{RESOURCES_DIRNAME}/ not found relative to mcp-coder package")


def resources_dir() -> Path:
    return repo_root() / RESOURCES_DIRNAME
