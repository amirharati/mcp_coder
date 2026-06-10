"""CLI: mcp-coder setup — print workspace info and the mcp.json block for Cursor."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from core.config import apply_provider_env, load_env_files
from core.config.role_models import (
    ROLE_CONTEXT_BUILDER,
    ROLE_EXECUTOR,
    ROLE_REVIEW,
    _ROLE_MODEL_ENV,
    _ROLE_MODEL_YAML,
    resolve_role_model_name,
)
from core.storage.paths import mcp_coder_home, workspace_config_path
from core.storage.workspace_config import load_workspace_config

WriteTarget = Literal["global", "local"]

_RESTART_HINT = "Restart Cursor (or Settings → MCP) to connect."
_ACTION_HINT = (
    "→  Run 'mcp-coder setup --local' to wire this project, "
    "or '--global' for all Cursor projects."
)


def _binary_path() -> str:
    """Return the absolute path to the mcp-coder binary."""
    exe = shutil.which("mcp-coder")
    if exe:
        return str(Path(exe).resolve())
    return str(Path(sys.argv[0]).resolve())


def _home_display() -> str:
    """Return a display string for the mcp-coder home directory."""
    home_env = os.environ.get("MCP_CODER_HOME", "").strip()
    home = mcp_coder_home()
    try:
        rel = home.relative_to(Path.home())
        display = f"~/{rel}"
    except ValueError:
        display = str(home)
    if home_env:
        return f"{display}  (MCP_CODER_HOME)"
    return display


def _executor_source_label() -> str:
    """Return the env var name or 'default' for the executor model."""
    for key in ("AIDER_MODEL", "MCP_CODER_MODEL"):
        if os.environ.get(key, "").strip():
            return key
    return "default"


def _role_source_label(role: str, workspace: str | Path) -> str:
    """Return the source label for a non-executor role, or '' if falling back."""
    env_var = _ROLE_MODEL_ENV.get(role)
    if env_var and os.environ.get(env_var, "").strip():
        return env_var

    yaml_key = _ROLE_MODEL_YAML.get(role)
    if yaml_key:
        ws_value = load_workspace_config(workspace).get(yaml_key)
        if isinstance(ws_value, str) and ws_value.strip():
            return "config.yaml"

    return ""


def _global_mcp_json_path() -> Path | None:
    """OS-specific Cursor global mcp.json path (macOS/Linux only)."""
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library/Application Support/Cursor/User/globalStorage/cursor-dev.cursor-mcp/mcp.json"
        )
    if sys.platform.startswith("linux"):
        return (
            Path.home()
            / ".config/Cursor/User/globalStorage/cursor-dev.cursor-mcp/mcp.json"
        )
    return None


def _local_mcp_json_path() -> Path:
    return Path.cwd().resolve() / ".cursor" / "mcp.json"


def _display_path(path: Path) -> str:
    try:
        return "~" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _build_mcp_coder_entry(*, binary: str, env_file: str) -> dict[str, object]:
    return {
        "command": binary,
        "env": {
            "MCP_CODER_ENV_FILE": env_file,
        },
    }


def _merge_and_write_mcp_json(path: Path, entry: dict[str, object]) -> tuple[str, bool]:
    """
    Merge mcp-coder entry into path. Creates parent dirs if needed.

    Returns (action, had_mcp_coder) where action is 'created' or 'updated'.
    Raises ValueError on invalid JSON (file is not modified).
    """
    had_file = path.is_file()
    if had_file:
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON in {path}: root must be an object")
    else:
        data = {}

    mcp_servers = data.get("mcpServers")
    had_mcp_coder = isinstance(mcp_servers, dict) and "mcp-coder" in mcp_servers
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}

    mcp_servers = dict(mcp_servers)
    mcp_servers["mcp-coder"] = entry
    data["mcpServers"] = mcp_servers

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    if not had_file:
        return "created", False
    return "updated", had_mcp_coder


def _write_mcp_json_target(write_target: WriteTarget, entry: dict[str, object]) -> int:
    if write_target == "local":
        path = _local_mcp_json_path()
        display = ".cursor/mcp.json"
    else:
        global_path = _global_mcp_json_path()
        if global_path is None:
            print(
                "Error: --global is not supported on this OS. "
                "Use --local or paste the mcp.json block manually.",
                file=sys.stderr,
            )
            return 1
        path = global_path
        display = _display_path(path)

    try:
        action, had_mcp_coder = _merge_and_write_mcp_json(path, entry)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if action == "created":
        print(f"Created {display}  ✓")
    elif had_mcp_coder:
        print(f"Updated {display} — mcp-coder entry updated  ✓")
    else:
        print(
            f"Updated {display} — mcp-coder entry added (other servers unchanged)  ✓"
        )

    print(_RESTART_HINT)
    return 0


def _init_workspace_config(cwd: str) -> int:
    config_path = workspace_config_path(cwd)
    rel_config = ".mcp-coder/config.yaml"
    if config_path.is_file():
        print(
            f"Error: {rel_config} already exists. Remove it first to reinitialize.",
            file=sys.stderr,
        )
        return 1
    example_path = Path(__file__).resolve().parents[2] / "resources" / "examples" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(example_path), str(config_path))
    print(f"Created: {config_path}")
    return 0


def run_setup(
    *,
    init_config: bool = False,
    write_target: WriteTarget | None = None,
) -> int:
    """Print workspace setup info and optionally write mcp.json. Returns exit code."""
    loaded_env_files = load_env_files()
    apply_provider_env()

    cwd = str(Path.cwd().resolve())
    binary = _binary_path()
    primary_env_file = loaded_env_files[0] if loaded_env_files else None
    env_for_block = str(primary_env_file) if primary_env_file else "/path/to/.env"
    mcp_entry = _build_mcp_coder_entry(binary=binary, env_file=env_for_block)

    if write_target is not None:
        rc = _write_mcp_json_target(write_target, mcp_entry)
        if rc != 0:
            return rc
        if init_config:
            init_rc = _init_workspace_config(cwd)
            if init_rc != 0:
                return init_rc
        return 0

    home_display = _home_display()

    print("mcp-coder setup")
    print("===============")
    print(f"Workspace:   {cwd}")
    print(f"mcp-coder:   {binary}")
    print(f"Home:        {home_display}")
    print()

    if primary_env_file:
        print(f"Env file:    {primary_env_file}  (found)")
    else:
        print("Env file:    (not found)")
        print(
            "  Tip: create a .env file in this directory or the mcp-coder repo root "
            "and add your OPENROUTER_API_KEY (or ANTHROPIC_API_KEY, OPENAI_API_KEY)."
        )

    executor_model = resolve_role_model_name(ROLE_EXECUTOR, cwd)
    cb_model = resolve_role_model_name(ROLE_CONTEXT_BUILDER, cwd)
    review_model = resolve_role_model_name(ROLE_REVIEW, cwd)

    executor_src = _executor_source_label()
    cb_src = _role_source_label(ROLE_CONTEXT_BUILDER, cwd)
    review_src = _role_source_label(ROLE_REVIEW, cwd)

    print("Models:")
    print(f"  executor:         {executor_model}  (from {executor_src})")

    if cb_src:
        print(f"  context_builder:  {cb_model}  (from {cb_src})")
    else:
        print("  context_builder:  (falls back to executor)")

    if review_src:
        print(f"  review:           {review_model}  (from {review_src})")
    else:
        print("  review:           (falls back to executor)")

    print()

    mcp_block = {"mcpServers": {"mcp-coder": mcp_entry}}
    print("Cursor mcp.json block — paste into ~/Library/.../mcp.json or .cursor/mcp.json:")
    print()
    print(json.dumps(mcp_block, indent=2))
    print()

    config_path = workspace_config_path(cwd)
    rel_config = ".mcp-coder/config.yaml"
    if config_path.is_file():
        print(f"Workspace config:  {rel_config}  (present)")
    else:
        print(f"Workspace config:  {rel_config}  (not found — run with --init-config to create)")

    print()
    print(_ACTION_HINT)

    if init_config:
        return _init_workspace_config(cwd)

    return 0


def main_setup(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Print workspace info and the mcp.json block to paste into Cursor.",
    )
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--global",
        dest="setup_global",
        action="store_true",
        help="Merge mcp-coder entry into the system-wide Cursor mcp.json",
    )
    target_group.add_argument(
        "--local",
        dest="setup_local",
        action="store_true",
        help="Merge mcp-coder entry into .cursor/mcp.json in the current directory",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Create .mcp-coder/config.yaml from the bundled example if absent (never overwrites).",
    )
    args = parser.parse_args(argv)

    write_target: WriteTarget | None = None
    if args.setup_global:
        write_target = "global"
    elif args.setup_local:
        write_target = "local"

    return run_setup(init_config=args.init_config, write_target=write_target)
