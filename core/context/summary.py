from __future__ import annotations

import hashlib
import re

PROMPT_SEPARATOR = "\n\n---\n\n"
PROMPT_PREVIEW_CHARS = 500


def assemble_prompt(context_summary: str, task: str) -> str:
    """Build the prompt sent to Aider from Cursor fallback context + task."""
    parts = [p.strip() for p in (context_summary, task) if p and p.strip()]
    if not parts:
        return task.strip() if task else ""
    if len(parts) == 1:
        return parts[0]
    return PROMPT_SEPARATOR.join(parts)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English prose/code mix)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_metadata(prompt: str, *, context_summary: str) -> dict[str, object]:
    preview = prompt[:PROMPT_PREVIEW_CHARS]
    if len(prompt) > PROMPT_PREVIEW_CHARS:
        preview += "…"
    return {
        "fallback_summary_hash": sha256_hex(context_summary),
        "prompt_chars": len(prompt),
        "prompt_tokens_est": estimate_tokens(prompt),
        "prompt_hash": sha256_hex(prompt),
        "prompt_preview": preview,
    }


def redact_secrets(text: str) -> str:
    """Best-effort redaction of common API key patterns in log payloads."""
    patterns = [
        (r"(sk-[a-zA-Z0-9]{20,})", "sk-***"),
        (r"(ANTHROPIC_API_KEY=)[^\s]+", r"\1***"),
        (r"(OPENAI_API_KEY=)[^\s]+", r"\1***"),
        (r"(OPENROUTER_API_KEY=)[^\s]+", r"\1***"),
    ]
    out = text
    for pattern, repl in patterns:
        out = re.sub(pattern, repl, out)
    return out
