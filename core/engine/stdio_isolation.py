from __future__ import annotations

import contextlib
import io
import logging
import sys
from collections.abc import Generator
from typing import Any

# Loggers that often write to stderr during Aider / LiteLLM runs.
_QUIET_LOGGERS = (
    "aider",
    "litellm",
    "httpx",
    "httpcore",
    "openai",
    "LiteLLM",
)


@contextlib.contextmanager
def isolated_stdio() -> Generator[tuple[io.StringIO, io.StringIO], None, None]:
    """
    Keep Aider/LiteLLM chatter off the real stdout/stderr.

    MCP stdio transport requires stdout to be JSON-only; any print() breaks Cursor.
    """
    stdout_cap = io.StringIO()
    stderr_cap = io.StringIO()
    previous_levels = {name: logging.getLogger(name).level for name in _QUIET_LOGGERS}
    try:
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.ERROR)
        with contextlib.redirect_stdout(stdout_cap), contextlib.redirect_stderr(stderr_cap):
            yield stdout_cap, stderr_cap
    finally:
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)


def bind_aider_io_to_buffer(io_obj: Any, buffer: io.StringIO) -> None:
    """Route Rich console and io.print() to the capture buffer (Aider defaults to terminal)."""
    from rich.console import Console

    io_obj.console = Console(file=buffer, force_terminal=False, no_color=True)

    def _print(message: str = "") -> None:
        buffer.write(str(message))
        if message and not str(message).endswith("\n"):
            buffer.write("\n")

    io_obj.print = _print  # type: ignore[method-assign]


def merged_capture(*buffers: io.StringIO) -> str:
    parts = [b.getvalue().strip() for b in buffers if b.getvalue().strip()]
    return "\n".join(parts)
