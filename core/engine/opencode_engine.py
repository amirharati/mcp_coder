"""
OpenCode adapter (placeholder).

Phase 1 ships Aider only. To add OpenCode later:
  1. Subclass ExecutionEngine
  2. Implement run() (likely subprocess: opencode run …)
  3. Decorate with @register_engine("opencode")
  4. Document env/deps in docs/INSTALL.md

from core.engine.base import ExecutionEngine, ExecutionResult
from core.engine.factory import register_engine

BACKEND_ID = "opencode"


@register_engine(BACKEND_ID)
class OpenCodeEngine(ExecutionEngine):
    @property
    def backend_id(self) -> str:
        return BACKEND_ID

    def run(self, prompt, target_files, *, workspace_path):
        raise NotImplementedError("OpenCode adapter not implemented yet")
"""
