"""Backend LLM interception contract (D-P8-5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InterceptionStrategy = Literal["subclass", "proxy", "callback"]


@dataclass(frozen=True)
class InterceptionProfile:
    """Declarative description of how a backend's LLM calls are intercepted."""

    strategy: InterceptionStrategy
    verified_call_sites: tuple[str, ...]
    known_gaps: tuple[str, ...]
    thinking_captured: bool


AIDER_INTERCEPTION_PROFILE = InterceptionProfile(
    strategy="subclass",
    verified_call_sites=("aider/models.py:970",),
    known_gaps=(
        "warm_cache_worker (base_coder.py:1373) bypasses send_completion — covered by Route A callback",
    ),
    thinking_captured=True,
)
