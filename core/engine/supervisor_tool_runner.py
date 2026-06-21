"""SupervisorToolRunner — two-tier context + tool-calling loop (P12-003, D-P12-7/8).

Wraps ``LlmGateway.complete()`` with a tool registry so the Supervisor LLM can be
handed a compact base context (tier 1) plus a set of tools (tier 2) it may call on
demand before issuing a final decision. The runner is backend-neutral: it calls
``gw.complete()`` directly (not ``run_owned_helper_completion``) per D-P12-8 and never
imports Aider APIs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.config.role_models import ROLE_SUPERVISOR
from core.observability.gateway import GatewayCompletion, get_llm_gateway

# Per-tool result budget in characters. Module constant for Phase 12 (D-P12-8);
# Phase 13 may make it configurable via env.
_TOOL_RESULT_BUDGET = 2000


class SupervisorToolRunner:
    """Tool-calling loop for Supervisor LLM decisions.

    Wraps gw.complete() with a tool registry. On each iteration:
    - If the model returns tool_calls: execute tools, append results, loop.
    - If no tool_calls: return the text response as the final answer.
    - After max_tool_rounds with no final text: do one final call without tools.

    SupervisorToolRunner calls gw.complete() directly (not run_owned_helper_completion).
    """

    def __init__(
        self,
        *,
        model: str,
        workspace_path: str,
        event_sink: Callable[[dict], None] | None = None,
        max_tool_rounds: int = 3,
    ) -> None:
        self._model = model
        self._workspace_path = workspace_path
        self._event_sink = event_sink
        self._max_tool_rounds = max(1, int(max_tool_rounds))
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        schema: dict,
        fn: Callable[..., str],
    ) -> None:
        """Register a tool by name with its description, JSON-Schema params, and callable."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "schema": schema,
            "fn": fn,
        }

    def run(self, system_prompt: str, messages: list[dict]) -> str:
        """Run the tool-calling loop. Returns the Supervisor's final text response."""
        gw = get_llm_gateway()
        all_messages: list[dict] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(list(messages))
        tools_spec = self._build_tools_spec()

        for _round in range(self._max_tool_rounds):
            completion = gw.complete(
                model=self._model,
                messages=all_messages,
                role=ROLE_SUPERVISOR,
                tools=tools_spec if tools_spec else None,
            )
            if completion.error:
                return ""

            if not completion.tool_calls:
                # Final answer — no tool calls requested.
                return completion.text

            # Append the assistant's tool-call message before the results.
            all_messages.append(
                {
                    "role": "assistant",
                    "content": completion.text or "",
                    "tool_calls": completion.tool_calls,
                }
            )
            for tc in completion.tool_calls:
                result_text = self._execute_tool(tc)
                self._emit_tool_call_event(tc, result_text, completion)
                all_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": result_text,
                    }
                )

        # max_tool_rounds reached — do one final call without tools.
        completion = gw.complete(
            model=self._model,
            messages=all_messages,
            role=ROLE_SUPERVISOR,
            tools=None,
        )
        return completion.text

    def _build_tools_spec(self) -> list[dict]:
        """Build the OpenAI function-calling tool spec from the registry."""
        spec: list[dict] = []
        for entry in self._tools.values():
            spec.append(
                {
                    "type": "function",
                    "function": {
                        "name": entry["name"],
                        "description": entry["description"],
                        "parameters": entry["schema"],
                    },
                }
            )
        return spec

    def _execute_tool(self, tc: dict) -> str:
        """Parse tool call, execute fn, return result string (truncated to budget)."""
        name = tc.get("name", "")
        entry = self._tools.get(name)
        if entry is None:
            return f"[tool_error] unknown tool: {name}"
        try:
            import json

            kwargs = json.loads(tc.get("arguments") or "{}")
            result = entry["fn"](**kwargs)
            return str(result)[:_TOOL_RESULT_BUDGET]
        except Exception as exc:
            return f"[tool_error] {name}: {exc}"

    def _emit_tool_call_event(
        self, tc: dict, result: str, completion: GatewayCompletion
    ) -> None:
        if self._event_sink is None:
            return
        try:
            self._event_sink(
                {
                    "type": "supervisor_tool_call",
                    "tool": tc.get("name"),
                    "args_summary": str(tc.get("arguments") or "")[:200],
                    "result_chars": len(result),
                    "result_preview": result[:120],
                    "model": completion.model,
                    "duration_ms": completion.duration_ms,
                }
            )
        except Exception:
            pass  # observability must never break the loop


# ── Phase 12 built-in tools ───────────────────────────────────────────────────


def _get_project_state_fn(project_state) -> str:
    import json

    d = {
        "decisions": project_state.decisions[-10:],
        "open_risks": project_state.open_risks[-10:],
        "hot_areas": project_state.hot_areas[:20],
        "last_delegation": project_state.last_delegation,
    }
    return json.dumps(d, ensure_ascii=False)[:_TOOL_RESULT_BUDGET]


def _get_delegation_history_fn(workspace_path, project_key, limit=5) -> str:
    import json

    from core.workspace.history_query import list_delegations

    limit = max(1, min(10, int(limit)))
    rows = list_delegations(workspace_path, limit=limit * 3)
    prefix = project_key.split("/")[0] if project_key else ""
    filtered = [
        r
        for r in rows
        if not prefix or (r.get("spec_path") or "").startswith(prefix)
    ][:limit]
    summaries = []
    for r in filtered:
        summaries.append(
            {
                "id": str(r.get("delegation_id") or "")[:8],
                "spec_path": r.get("spec_path"),
                "outcome": r.get("outcome"),
                "files_changed": (r.get("files_changed") or [])[:5],
                "task": str(r.get("task") or "")[:120],
            }
        )
    return json.dumps(summaries, ensure_ascii=False)[:_TOOL_RESULT_BUDGET]


def _read_file_fn(workspace_path, path) -> str:
    rel = str(path or "")
    if ".." in rel.replace("\\", "/").split("/"):
        return "[tool_error] path traversal not allowed"
    target = Path(workspace_path) / rel
    try:
        if not target.is_file():
            return "[tool_error] file not found"
        return target.read_text(encoding="utf-8", errors="replace")[:_TOOL_RESULT_BUDGET]
    except Exception as exc:
        return f"[tool_error] read_file: {exc}"


def build_phase12_tool_runner(
    *,
    workspace_path: str,
    project_key: str,
    project_state,
    event_sink: Callable[[dict], None] | None,
    model: str,
) -> SupervisorToolRunner:
    """Build a SupervisorToolRunner pre-registered with the three Phase 12 tools."""
    runner = SupervisorToolRunner(
        model=model,
        workspace_path=workspace_path,
        event_sink=event_sink,
    )

    runner.register_tool(
        name="get_project_state",
        description=(
            "Get the current project state: decisions, open risks, hot areas, "
            "last delegation. Use when deciding if this task conflicts with a prior "
            "decision or touches a risky area."
        ),
        schema={"type": "object", "properties": {}},
        fn=lambda: _get_project_state_fn(project_state),
    )

    runner.register_tool(
        name="get_delegation_history",
        description=(
            "Get a summary of recent delegations for this project. Use when you "
            "need to know what was implemented in previous tasks, what failed, or "
            "what files were changed recently."
        ),
        schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max delegations to return (1-10)",
                    "default": 5,
                }
            },
        },
        fn=lambda limit=5: _get_delegation_history_fn(
            workspace_path, project_key, limit=limit
        ),
    )

    runner.register_tool(
        name="read_file",
        description=(
            "Read the contents of a file in the workspace. Use when you need to "
            "understand what a specific file currently contains before deciding "
            "whether to rerun or escalate."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within workspace",
                }
            },
            "required": ["path"],
        },
        fn=lambda path: _read_file_fn(workspace_path, path),
    )

    return runner
