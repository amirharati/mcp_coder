from __future__ import annotations

import io
import os
import re
from typing import Any

OUTCOME_SUCCESS = "success"
OUTCOME_NEEDS_INPUT_FILES = "needs_input_files"
OUTCOME_NEEDS_INPUT_CLARIFICATION = "needs_input_clarification"
OUTCOME_FAILURE = "failure"

STALL_OUTPUT_TAIL_CHARS = 500

# Defaults for MCP delegations — non-interactive, no git commits from Aider.
# Override via MCP_CODER_AIDER_* or AIDER_* env (see .env.example).


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def delegation_auto_commits() -> bool:
    if os.environ.get("MCP_CODER_AIDER_AUTO_COMMITS") is not None:
        return _env_bool("MCP_CODER_AIDER_AUTO_COMMITS", False)
    if os.environ.get("AIDER_AUTO_COMMITS") is not None:
        return _env_bool("AIDER_AUTO_COMMITS", False)
    return False


def delegation_dirty_commits() -> bool:
    if os.environ.get("MCP_CODER_AIDER_DIRTY_COMMITS") is not None:
        return _env_bool("MCP_CODER_AIDER_DIRTY_COMMITS", False)
    if os.environ.get("AIDER_DIRTY_COMMITS") is not None:
        return _env_bool("AIDER_DIRTY_COMMITS", False)
    return False


def delegation_use_git() -> bool:
    """Keep git for diffs; set MCP_CODER_AIDER_USE_GIT=0 for --no-git."""
    return _env_bool("MCP_CODER_AIDER_USE_GIT", _env_bool("AIDER_USE_GIT", True))


def delegation_suggest_shell() -> bool:
    return _env_bool("MCP_CODER_AIDER_SUGGEST_SHELL", False)


def delegation_stream() -> bool:
    return _env_bool("MCP_CODER_AIDER_STREAM", False)


def delegation_auto_lint() -> bool:
    return _env_bool("MCP_CODER_AIDER_AUTO_LINT", False)


def delegation_detect_urls() -> bool:
    """Whether Aider should scrape URLs found in prompts (default: False for MCP delegations).

    Set MCP_CODER_AIDER_DETECT_URLS=1 to opt in.  Was implicitly True before P2-125.
    """
    return _env_bool("MCP_CODER_AIDER_DETECT_URLS", False)


def delegation_timeout_seconds() -> float:
    """Max seconds for a single delegate_to_agent engine run (default 120).

    Override via MCP_CODER_DELEGATION_TIMEOUT_S.
    """
    raw = os.environ.get("MCP_CODER_DELEGATION_TIMEOUT_S", "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return 120.0


# ── Bounded executor outer-loop limits (P7-002, D-P7-2/Q6) ──────────────────


def resolve_executor_hard_max() -> int:
    """Hard ceiling for executor steps: always 20 regardless of env."""
    return 20


def resolve_executor_max_steps() -> int:
    """Max executor steps per delegation (default 10, clamped to [1, hard_max]).

    Override via MCP_CODER_EXECUTOR_MAX_STEPS.
    """
    hard_max = resolve_executor_hard_max()
    raw = os.environ.get("MCP_CODER_EXECUTOR_MAX_STEPS", "").strip()
    if raw:
        try:
            v = int(raw)
            if v >= 1:
                return min(v, hard_max)
        except ValueError:
            pass
    return min(10, hard_max)


def resolve_executor_step_timeout_s() -> float:
    """Per-step timeout in seconds (default 300).

    Override via MCP_CODER_EXECUTOR_STEP_TIMEOUT_S.
    """
    raw = os.environ.get("MCP_CODER_EXECUTOR_STEP_TIMEOUT_S", "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return 300.0


def resolve_executor_total_timeout_s() -> float:
    """Total delegation timeout across all steps in seconds (default 1800).

    Override via MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S.
    """
    raw = os.environ.get("MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S", "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return 1800.0


def create_delegation_io() -> tuple[Any, io.StringIO]:
    """
  InputOutput for headless delegation (~ aider --yes-always --no-auto-commits).

  Returns (io, buffer) so callers can read captured tool output.

  Must be called inside core.engine.stdio_isolation.isolated_stdio() so Aider
  init does not write to the process stdout (breaks MCP JSON-RPC).
  """
    from aider.io import InputOutput

    from core.engine.stdio_isolation import bind_aider_io_to_buffer

    buffer = io.StringIO()
    io_obj = InputOutput(
        pretty=False,
        yes=True,
        fancy_input=False,
        output=buffer,
    )
    bind_aider_io_to_buffer(io_obj, buffer)
    return io_obj, buffer


def delegation_coder_kwargs(edit_format: str | None = None) -> dict[str, Any]:
    """Keyword args for Coder.create() during MCP delegations.

    Pass `edit_format` (e.g. "whole", "diff") to override the model-native format
    resolved from CallParams.  None → let Aider pick based on the model.
    """
    kwargs: dict[str, Any] = {
        "auto_commits": delegation_auto_commits(),
        "dirty_commits": delegation_dirty_commits(),
        "use_git": delegation_use_git(),
        "suggest_shell_commands": delegation_suggest_shell(),
        "stream": delegation_stream(),
        "auto_lint": delegation_auto_lint(),
        "show_diffs": False,
        # URL scrape via Playwright when prompt contains https://.
        # Default False for MCP delegations (P2-125 BL-309a); opt in via env.
        "detect_urls": delegation_detect_urls(),
    }
    if edit_format:
        kwargs["edit_format"] = edit_format
    return kwargs


_FILES_REQUEST_MARKERS = (
    "add these files to the chat",
    "add the following files to the chat",
    "could you please add",
    "please add these files",
    "please add the following files",
    "i need access to the existing files",
    "i need access to",
    "add them to the chat",
    "add it to the chat",
    "add this file to the chat",
    "add the file to the chat",
    "add to the chat",
)

_CLARIFICATION_MARKERS = (
    "i need to know",
    "could you clarify",
    "please clarify",
    "can you clarify",
    "which approach",
    "which option",
    "before i can proceed",
    "before we proceed",
    "can you tell me",
    "would you prefer",
    "do you want me to",
    "should i use",
)

_PATH_IN_BACKTICKS_RE = re.compile(
    r"`((?:[\w./-]+/)?[\w./-]+\.(?:py|md|yaml|yml|json|txt|ts|tsx|js|jsx|toml|cfg|ini|sh|html|css))`",
    re.IGNORECASE,
)
_ADD_FILE_TO_CHAT_RE = re.compile(
    r"(?:add|include)\s+[`'\"]?((?:[\w./-]+/)?[\w./-]+\.[\w]+)[`'\"]?\s+to\s+the\s+chat",
    re.IGNORECASE,
)
_BARE_FILE_PATH_RE = re.compile(
    r"(?<![\w./])([\w./-]+\.(?:py|md|yaml|yml|json|txt|ts|tsx|js|jsx|toml|cfg|ini|sh|html|css))(?![\w.])",
    re.IGNORECASE,
)


def stall_auto_retry_enabled() -> bool:
    """One-shot auto-retry when executor stalls asking for files (default off)."""
    return _env_bool("MCP_CODER_STALL_AUTO_RETRY", False)


def _executor_text(*, output: str, partial_response: str | None) -> str:
    return "\n".join(filter(None, [output, partial_response or ""])).strip()


def _executor_output_tail(text: str, *, max_chars: int = STALL_OUTPUT_TAIL_CHARS) -> str:
    compact = text.strip()
    if len(compact) <= max_chars:
        return compact
    return compact[-max_chars:]


def _normalize_requested_path(raw: str) -> str | None:
    path = (raw or "").strip().strip("`\"'")
    if not path or path.startswith("http"):
        return None
    return path.replace("\\", "/")


def extract_requested_file_paths(text: str) -> list[str]:
    """Extract deduped repo-relative file paths from Aider stall output."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_PATH_IN_BACKTICKS_RE, _ADD_FILE_TO_CHAT_RE):
        for match in pattern.finditer(text):
            normalized = _normalize_requested_path(match.group(1))
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)
    lower = text.lower()
    if any(marker in lower for marker in _FILES_REQUEST_MARKERS):
        for match in _BARE_FILE_PATH_RE.finditer(text):
            normalized = _normalize_requested_path(match.group(1))
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)
    return found


def _looks_like_files_request(lower: str) -> bool:
    return any(marker in lower for marker in _FILES_REQUEST_MARKERS) or bool(
        _ADD_FILE_TO_CHAT_RE.search(lower)
    )


def _looks_like_clarification(lower: str, text: str) -> bool:
    if any(marker in lower for marker in _CLARIFICATION_MARKERS):
        return True
    if "?" in text and not _looks_like_files_request(lower):
        return True
    return False


def classify_executor_outcome(
    *,
    io: Any,
    output: str,
    partial_response: str | None,
) -> dict[str, Any]:
    """Classify executor output into success / needs_input_* / failure (regex-only v0)."""
    if getattr(io, "num_error_outputs", 0) > 0:
        return {
            "outcome": OUTCOME_FAILURE,
            "message": "Aider reported one or more errors (see output)",
            "files_requested": [],
            "executor_output_tail": _executor_output_tail(_executor_text(output=output, partial_response=partial_response)),
        }

    text = _executor_text(output=output, partial_response=partial_response)
    lower = text.lower()
    error_markers = (
        "litellm.",
        "notfounderror",
        "authenticationerror",
        "ratelimiterror",
        "openrouterexception",
        "openaierror",
        "playwright sync api",
    )
    if any(marker in lower for marker in error_markers):
        return {
            "outcome": OUTCOME_FAILURE,
            "message": text[:2000] or "LLM provider error",
            "files_requested": [],
            "executor_output_tail": _executor_output_tail(text),
        }
    if not text:
        return {
            "outcome": OUTCOME_FAILURE,
            "message": "Empty response from Aider (no edits applied?)",
            "files_requested": [],
            "executor_output_tail": "",
        }

    if _looks_like_files_request(lower):
        files_requested = extract_requested_file_paths(text)
        return {
            "outcome": OUTCOME_NEEDS_INPUT_FILES,
            "message": "Aider needs additional files. Add them to target_files and retry.",
            "files_requested": files_requested,
            "executor_output_tail": _executor_output_tail(text),
        }

    if _looks_like_clarification(lower, text):
        return {
            "outcome": OUTCOME_NEEDS_INPUT_CLARIFICATION,
            "message": (
                "Aider requested clarification before implementing "
                "(use mode=review or expand context_summary)."
            ),
            "files_requested": [],
            "executor_output_tail": _executor_output_tail(text),
        }

    return {
        "outcome": OUTCOME_SUCCESS,
        "message": None,
        "files_requested": [],
        "executor_output_tail": _executor_output_tail(text),
    }


def build_needs_input_payload(classification: dict[str, Any]) -> dict[str, Any]:
    """Structured needs_input block for MCP response."""
    stall_type = classification.get("outcome")
    reason = (
        "executor_requested_files"
        if stall_type == OUTCOME_NEEDS_INPUT_FILES
        else "executor_requested_clarification"
    )
    payload: dict[str, Any] = {
        "status": "needs_input",
        "reason": reason,
        "message": classification.get("message") or "",
        "executor_output_tail": classification.get("executor_output_tail") or "",
    }
    files_requested = classification.get("files_requested") or []
    if files_requested:
        payload["files_requested"] = list(files_requested)
    return payload


def infer_run_success(
    *,
    io: Any,
    output: str,
    partial_response: str | None,
) -> tuple[bool, str | None]:
    """Treat Aider/LiteLLM tool errors and interactive questions as implement failure."""
    classification = classify_executor_outcome(
        io=io,
        output=output,
        partial_response=partial_response,
    )
    if classification["outcome"] == OUTCOME_SUCCESS:
        return True, None
    return False, classification.get("message")
