from __future__ import annotations

import os
from typing import Callable, TypeVar, overload

from core.engine.base import ExecutionEngine

T = TypeVar("T", bound=type[ExecutionEngine])

DEFAULT_BACKEND = "aider"
_REGISTRY: dict[str, type[ExecutionEngine]] = {}


class UnknownBackendError(ValueError):
    def __init__(self, backend: str, available: list[str]) -> None:
        self.backend = backend
        self.available = available
        super().__init__(
            f"Unsupported backend {backend!r}. "
            f"Available: {', '.join(available) or '(none registered)'}"
        )


@overload
def register_engine(backend_id: str, engine_cls: T) -> T: ...


@overload
def register_engine(backend_id: str) -> Callable[[T], T]: ...


def register_engine(
    backend_id: str,
    engine_cls: T | None = None,
) -> T | Callable[[T], T]:
    """Register an adapter class (decorator or direct call)."""

    def _register(cls: T) -> T:
        key = backend_id.strip().lower()
        if not key:
            raise ValueError("backend_id must be non-empty")
        _REGISTRY[key] = cls
        return cls

    if engine_cls is not None:
        return _register(engine_cls)
    return _register


def list_backends() -> list[str]:
    return sorted(_REGISTRY)


def default_backend() -> str:
    return os.environ.get("MCP_CODER_DEFAULT_BACKEND", DEFAULT_BACKEND).strip().lower()


def get_engine(backend: str | None = None, **kwargs: object) -> ExecutionEngine:
  """
  Resolve and instantiate an execution adapter.

  Args:
    backend: MCP `backend` argument; falls back to MCP_CODER_DEFAULT_BACKEND or `aider`.
    **kwargs: Passed to the adapter constructor (e.g. model_name for Aider).
  """
  key = (backend or default_backend()).strip().lower()
  engine_cls = _REGISTRY.get(key)
  if engine_cls is None:
    raise UnknownBackendError(key, list_backends())
  engine = engine_cls(**kwargs)  # type: ignore[arg-type]
  profile = engine.interception_profile
  if not profile.thinking_captured:
    from core.observability import get_observability

    get_observability().warn(
      "interception_thinking_not_captured",
      {
        "backend": engine.backend_id,
        "strategy": profile.strategy,
        "known_gaps": list(profile.known_gaps),
      },
    )
  return engine
