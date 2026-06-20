"""CLI: ping the configured LLM (same env + Aider Model stack as delegations)."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
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
    from core.observability import CLI_FALLBACK_ROLE, role_context
    from core.observability.bootstrap import ensure_observability_bootstrap
    from core.observability.gateway import get_llm_gateway

    ensure_observability_bootstrap()

    t0 = time.perf_counter()
    try:
        with role_context(CLI_FALLBACK_ROLE):
            result = get_llm_gateway().complete(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                role=CLI_FALLBACK_ROLE,
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

    latency_ms = result.duration_ms or int((time.perf_counter() - t0) * 1000)
    if result.error:
        return ModelTestResult(
            ok=False,
            model=model,
            message=result.error,
            via="litellm",
            latency_ms=latency_ms,
        )

    reply = result.text
    tokens = result.tokens or {}
    usage = None
    if tokens.get("input") is not None or tokens.get("output") is not None:
        usage = {
            "input": tokens.get("input"),
            "output": tokens.get("output"),
            "total": tokens.get("total"),
            "prompt_tokens": tokens.get("input"),
            "completion_tokens": tokens.get("output"),
            "total_tokens": tokens.get("total"),
            "source": tokens.get("source") or "owned_completion",
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


_ROLES_ALL = ("executor", "context_builder", "review")


def run_test_model_all(
    *,
    prompt: str = "Reply with exactly: ok",
    max_tokens: int = 16,
    via: Via = "aider",
    workspace: str | Path | None = None,
) -> list[tuple[str, str, ModelTestResult, bool]]:
    """
    Ping each configured role's model sequentially.

    Returns a list of (role, model_id, result, is_fallback_from_executor).
    """
    from core.config.role_models import (
        ROLE_CONTEXT_BUILDER,
        ROLE_EXECUTOR,
        ROLE_PLANNER,
        ROLE_REVIEW,
        ROLE_REVIEWER,
        ROLE_SUPERVISOR,
        resolve_role_model_name,
    )

    load_env_files()
    apply_provider_env()

    ws = str(workspace) if workspace else str(Path.cwd().resolve())
    executor_model = resolve_role_model_name(ROLE_EXECUTOR, ws)

    rows: list[tuple[str, str, ModelTestResult, bool]] = []
    for role in (ROLE_EXECUTOR, ROLE_CONTEXT_BUILDER, ROLE_REVIEW, ROLE_SUPERVISOR, ROLE_PLANNER, ROLE_REVIEWER):
        model = resolve_role_model_name(role, ws)
        is_fallback = role != ROLE_EXECUTOR and model == executor_model
        result = run_test_model(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            via=via,
            print_resolution=False,
        )
        rows.append((role, model, result, is_fallback))

    return rows


def print_test_all_result(rows: list[tuple[str, str, ModelTestResult, bool]]) -> int:
    """Print tabulated --all results. Returns 0 if all pass, 1 if any fail."""
    role_width = max(len(role) for role, _, _, _ in rows)
    model_width = max(len(model) for _, model, _, _ in rows)

    print()
    for role, model, result, is_fallback in rows:
        status = "OK" if result.ok else "FAIL"
        lat = f"latency={result.latency_ms}ms" if result.latency_ms is not None else ""
        fallback_note = "  (fallback from executor)" if is_fallback else ""
        line = f"{role.ljust(role_width)}  {model.ljust(model_width)}  {status}"
        if lat:
            line += f"  {lat}"
        line += fallback_note
        print(line)
        if not result.ok:
            print(f"  Error: {result.message}", file=sys.stderr)

    print()
    total = len(rows)
    passed = sum(1 for _, _, r, _ in rows if r.ok)
    all_ok = passed == total
    if all_ok:
        print(f"All {total} passed.")
    else:
        print(f"{passed}/{total} passed.", file=sys.stderr)

    return 0 if all_ok else 1


def main_test_model(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Test AIDER_MODEL via Aider Model (default) or raw LiteLLM",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--model",
        help="Override model id (default: AIDER_MODEL → MCP_CODER_MODEL → built-in default)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Test all configured role models (executor, context_builder, review) sequentially",
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

    if args.all:
        rows = run_test_model_all(
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            via=args.via,
        )
        return print_test_all_result(rows)

    result = run_test_model(
        model=args.model,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        via=args.via,
    )
    print_test_result(result)
    return 0 if result.ok else 1
