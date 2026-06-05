"""CLI: ping the configured LLM (same env + Aider Model stack as delegations)."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from core.config import (
    DEFAULT_MODEL,
    apply_provider_env,
    load_env_files,
    provider_hint_for_model,
    resolve_model_name,
    resolve_openrouter_api_base,
)
from core.config.openrouter_models import openrouter_model_slug, validate_openrouter_model

Via = Literal["aider", "litellm", "both"]


@dataclass(frozen=True)
class ModelTestContext:
    env_files: tuple[str, ...]
    model: str
    model_source: str
    openrouter_api_base: str | None = None
    api_key_hint: str = "n/a"
    catalog_status: str | None = None


@dataclass(frozen=True)
class ModelTestResult:
    ok: bool
    model: str
    message: str
    via: Via = "aider"
    latency_ms: int | None = None
    reply: str | None = None
    usage: dict[str, Any] | None = None
    context: ModelTestContext | None = None
    extra_passes: tuple["ModelTestResult", ...] = field(default_factory=tuple)


def _mask_secret(value: str) -> str:
    raw = value.strip()
    if len(raw) <= 8:
        return "set (hidden)"
    return f"set ({raw[:4]}…{raw[-4:]})"


def _model_source(model_override: str | None) -> str:
    if (model_override or "").strip():
        return "--model"
    for key in ("AIDER_MODEL", "MCP_CODER_MODEL"):
        if os.environ.get(key, "").strip():
            return key
    return f"default ({DEFAULT_MODEL})"


def build_test_context(*, model_override: str | None = None) -> ModelTestContext:
    loaded = load_env_files()
    apply_provider_env()
    resolved = (model_override or "").strip() or resolve_model_name()

    api_key_hint = "n/a"
    api_base: str | None = None
    catalog_status: str | None = None

    if resolved.startswith("openrouter/"):
        api_base = resolve_openrouter_api_base()
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        api_key_hint = _mask_secret(key) if key else "missing"
        slug = openrouter_model_slug(resolved)
        if slug:
            catalog_error = validate_openrouter_model(resolved)
            catalog_status = "ok" if catalog_error is None else catalog_error

    return ModelTestContext(
        env_files=tuple(str(p) for p in loaded),
        model=resolved,
        model_source=_model_source(model_override),
        openrouter_api_base=api_base,
        api_key_hint=api_key_hint,
        catalog_status=catalog_status,
    )


def format_resolution(ctx: ModelTestContext) -> str:
    lines = [
        "Config resolution:",
        f"  env_files: {', '.join(ctx.env_files) if ctx.env_files else '(none loaded)'}",
        f"  model: {ctx.model}  (from {ctx.model_source})",
    ]
    if ctx.openrouter_api_base is not None:
        lines.append(f"  OPENROUTER_API_BASE: {ctx.openrouter_api_base}")
        lines.append(f"  OPENROUTER_API_KEY: {ctx.api_key_hint}")
    if ctx.catalog_status is not None:
        lines.append(f"  openrouter catalog: {ctx.catalog_status}")
    return "\n".join(lines)


def _ping_litellm(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ModelTestResult:
    t0 = time.perf_counter()
    try:
        import litellm

        litellm.suppress_debug_info = True
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ModelTestResult(
            ok=False,
            model=model,
            message=f"{type(exc).__name__}: {exc}",
            via="litellm",
            latency_ms=latency_ms,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        reply = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        reply = ""

    usage_raw = getattr(response, "usage", None)
    usage = None
    if usage_raw is not None:
        usage = {
            "prompt_tokens": getattr(usage_raw, "prompt_tokens", None),
            "completion_tokens": getattr(usage_raw, "completion_tokens", None),
            "total_tokens": getattr(usage_raw, "total_tokens", None),
        }

    if not reply.strip():
        return ModelTestResult(
            ok=False,
            model=model,
            message="Model returned an empty reply",
            via="litellm",
            latency_ms=latency_ms,
            reply=reply,
            usage=usage,
        )

    return ModelTestResult(
        ok=True,
        model=model,
        message="ok",
        via="litellm",
        latency_ms=latency_ms,
        reply=reply.strip(),
        usage=usage,
    )


def _ping_aider(*, model: str, prompt: str) -> ModelTestResult:
    """Same LiteLLM call path as Aider delegations (Model.send_completion + retries)."""
    from aider.models import Model

    t0 = time.perf_counter()
    try:
        aider_model = Model(model)
        reply = aider_model.simple_send_with_retries(
            [{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ModelTestResult(
            ok=False,
            model=model,
            message=f"{type(exc).__name__}: {exc}",
            via="aider",
            latency_ms=latency_ms,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = (reply or "").strip()
    if not text:
        return ModelTestResult(
            ok=False,
            model=model,
            message="Aider Model returned an empty reply",
            via="aider",
            latency_ms=latency_ms,
            reply=reply,
        )

    return ModelTestResult(
        ok=True,
        model=model,
        message="ok",
        via="aider",
        latency_ms=latency_ms,
        reply=text,
    )


def run_test_model(
    *,
    model: str | None = None,
    prompt: str = "Reply with exactly: ok",
    max_tokens: int = 16,
    via: Via = "aider",
    print_resolution: bool = True,
) -> ModelTestResult:
    ctx = build_test_context(model_override=model)
    if print_resolution:
        print(format_resolution(ctx), file=sys.stderr)

    resolved = ctx.model
    hint = provider_hint_for_model(resolved)
    if hint:
        return ModelTestResult(
            ok=False,
            model=resolved,
            message=hint,
            via=via,
            context=ctx,
        )

    if via == "litellm":
        result = _ping_litellm(model=resolved, prompt=prompt, max_tokens=max_tokens)
        return ModelTestResult(
            ok=result.ok,
            model=result.model,
            message=result.message,
            via=result.via,
            latency_ms=result.latency_ms,
            reply=result.reply,
            usage=result.usage,
            context=ctx,
        )

    if via == "aider":
        result = _ping_aider(model=resolved, prompt=prompt)
        return ModelTestResult(
            ok=result.ok,
            model=result.model,
            message=result.message,
            via=result.via,
            latency_ms=result.latency_ms,
            reply=result.reply,
            usage=result.usage,
            context=ctx,
        )

    aider_result = _ping_aider(model=resolved, prompt=prompt)
    litellm_result = _ping_litellm(
        model=resolved,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    ok = aider_result.ok and litellm_result.ok
    message = "ok" if ok else "one or more passes failed"
    return ModelTestResult(
        ok=ok,
        model=resolved,
        message=message,
        via="both",
        latency_ms=aider_result.latency_ms,
        reply=aider_result.reply if aider_result.ok else litellm_result.reply,
        usage=litellm_result.usage,
        context=ctx,
        extra_passes=(litellm_result,),
    )


def print_test_result(result: ModelTestResult) -> None:
    label = result.via
    if result.ok:
        print(f"OK  via={label}  model={result.model}  latency_ms={result.latency_ms}")
        print(f"reply: {result.reply}")
        if result.usage:
            print(f"usage: {result.usage}")
        for extra in result.extra_passes:
            print()
            print_test_result(extra)
        return

    print(f"FAIL  via={label}  model={result.model}", file=sys.stderr)
    if result.latency_ms is not None:
        print(f"latency_ms={result.latency_ms}", file=sys.stderr)
    print(result.message, file=sys.stderr)
    if result.reply:
        print(f"partial_reply: {result.reply}", file=sys.stderr)
    for extra in result.extra_passes:
        print(file=sys.stderr)
        print_test_result(extra)


def main_test_model(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Test AIDER_MODEL via Aider Model (default) or raw LiteLLM",
    )
    parser.add_argument(
        "--model",
        help="Override model id (default: AIDER_MODEL → MCP_CODER_MODEL → built-in default)",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: ok",
        help="User message for the ping (default: short echo test)",
    )
    parser.add_argument("--max-tokens", type=int, default=16, help="Max completion tokens (litellm only)")
    parser.add_argument(
        "--via",
        choices=("aider", "litellm", "both"),
        default="aider",
        help="aider = Model.simple_send_with_retries (delegation stack); litellm = direct completion",
    )
    args = parser.parse_args(argv)

    result = run_test_model(
        model=args.model,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        via=args.via,
    )
    print_test_result(result)
    return 0 if result.ok else 1
