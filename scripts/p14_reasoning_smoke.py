"""P14-003c dynamic smoke: ping a model matrix and report reasoning capture.

Usage:
  python scripts/p14_reasoning_smoke.py [--max-tokens 512] [--models ...]

Default model matrix covers the providers we want to harden against:
  - openrouter/anthropic/claude-sonnet-4.5
  - openrouter/deepseek/deepseek-v4-pro
  - openrouter/deepseek/deepseek-r1
  - openrouter/google/gemini-2.5-flash
  - openrouter/z-ai/glm-4.6
  - openrouter/openai/o3-mini
  - openrouter/meta-llama/llama-3.3-70b-instruct

Each model is pinged via LlmGateway.complete() (the helper call path) with a
prompt that elicits reasoning. The script reports, per model:
  - ok / error
  - reasoning_tokens (int or None)
  - reasoning_text present (bool)
  - latency_ms

Exit code 0 if every model that returned a 2xx also returned reasoning_tokens
(or has reasoning explicitly unavailable). Non-zero otherwise.

Requires OPENROUTER_API_KEY in env (loaded from .env).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MODELS = [
    "openrouter/anthropic/claude-sonnet-4.5",
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/deepseek/deepseek-r1",
    "openrouter/google/gemini-2.5-flash",
    "openrouter/z-ai/glm-4.6",
    "openrouter/openai/o3-mini",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
]

REASONING_PROMPT = (
    "A farmer has 100 meters of fence to enclose a rectangular field along a "
    "river (no fence needed on the river side). What dimensions maximize the "
    "area? Show your work step by step, then state the answer as WIDTHxHEIGHT."
)


@dataclass
class PingResult:
    model: str
    ok: bool
    error: str | None = None
    latency_ms: int | None = None
    reasoning_tokens: int | None = None
    reasoning_text_present: bool = False
    tokens: dict[str, Any] = field(default_factory=dict)


def _ensure_env() -> None:
    from core.config import apply_provider_env, load_env_files

    load_env_files()
    apply_provider_env()
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        print("ERROR: OPENROUTER_API_KEY not set (load .env or export it)", file=sys.stderr)
        sys.exit(2)


def _ping_one(*, model: str, max_tokens: int) -> PingResult:
    from core.config.model_registry import resolve
    from core.observability import CLI_FALLBACK_ROLE, role_context
    from core.observability.bootstrap import ensure_observability_bootstrap
    from core.observability.gateway import get_llm_gateway

    ensure_observability_bootstrap()
    t0 = time.perf_counter()
    try:
        with role_context(CLI_FALLBACK_ROLE):
            result = get_llm_gateway().complete(
                model=model,
                messages=[{"role": "user", "content": REASONING_PROMPT}],
                max_tokens=max_tokens,
                role=CLI_FALLBACK_ROLE,
            )
    except Exception as exc:
        return PingResult(
            model=model,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    latency_ms = result.duration_ms or int((time.perf_counter() - t0) * 1000)
    if result.error:
        return PingResult(
            model=model,
            ok=False,
            error=result.error,
            latency_ms=latency_ms,
            tokens=result.tokens or {},
        )

    tokens = result.tokens or {}
    return PingResult(
        model=model,
        ok=True,
        latency_ms=latency_ms,
        reasoning_tokens=tokens.get("reasoning_tokens"),
        reasoning_text_present=bool(result.reasoning_text),
        tokens=tokens,
    )


def _format_row(r: PingResult) -> str:
    status = "OK" if r.ok else "FAIL"
    rt = r.reasoning_tokens if r.reasoning_tokens is not None else "—"
    rtext = "yes" if r.reasoning_text_present else "no"
    err = f"  err={r.error}" if r.error else ""
    return f"{status:4}  {r.model:50} reasoning_tokens={rt!s:6} reasoning_text={rtext:3}  latency_ms={r.latency_ms}{err}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model ids to ping",
    )
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--json", action="store_true", help="Emit JSON results")
    args = parser.parse_args(argv)

    _ensure_env()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    # Force reasoning on for the cli_test role: high effort + OpenRouter-native
    # reasoning param via extra_body. This tests BOTH paths (litellm-native
    # reasoning_effort AND OpenRouter-native reasoning.effort) and ensures the
    # model actually engages its thinking channel on a hard prompt.
    os.environ.setdefault("MCP_CODER_CLI_TEST_REASONING_EFFORT", "high")
    os.environ.setdefault(
        "MCP_CODER_CLI_TEST_EXTRA_PARAMS",
        '{"extra_body": {"reasoning": {"effort": "high"}}}',
    )

    results: list[PingResult] = []
    for model in models:
        print(f"→ pinging {model} ...", file=sys.stderr)
        r = _ping_one(model=model, max_tokens=args.max_tokens)
        results.append(r)
        print(_format_row(r), file=sys.stderr)

    print(file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    # Pass = every model that returned ok must have reasoning_tokens OR an
    # explicit None (provider returned no reasoning). Failure = ok but
    # reasoning_text_present without reasoning_tokens (extraction gap), or
    # outright error.
    extraction_gaps = [
        r for r in results if r.ok and r.reasoning_text_present and r.reasoning_tokens is None
    ]
    hard_failures = [r for r in results if not r.ok]

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))

    if extraction_gaps:
        print(
            f"EXTRACTION GAPS ({len(extraction_gaps)}): reasoning_text present but "
            f"reasoning_tokens is None — extraction is not reading the usage field.",
            file=sys.stderr,
        )
        for r in extraction_gaps:
            print(f"  - {r.model}", file=sys.stderr)

    if hard_failures:
        print(f"HARD FAILURES ({len(hard_failures)}):", file=sys.stderr)
        for r in hard_failures:
            print(f"  - {r.model}: {r.error}", file=sys.stderr)

    passed = len(results) - len(hard_failures)
    print(
        f"\n{passed}/{len(results)} models returned ok. "
        f"{len(extraction_gaps)} extraction gaps.",
        file=sys.stderr,
    )
    return 0 if not extraction_gaps and not hard_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
