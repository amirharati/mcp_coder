# Phase 13 dogfood workspace

Isolated workspace for P13-001 CLI + Cursor dogfood of the Phase 12 persistent Supervisor architecture.

- **Workspace root:** this directory
- **MCP home (isolated):** `.mcp-coder-home/` (set `MCP_CODER_HOME` to this path during dogfood)
- **App package:** `habit_cli/` — built incrementally across delegations
- **Specs:** `.mcp-coder/specs/tasks/p13-habit-*.md` (created by harness or host)

Run CLI harness from repo root:

```bash
python scripts/p13_phase12_cli_dogfood.py --quick    # env + layout only
python scripts/p13_phase12_cli_dogfood.py --live     # 2 live delegations (LLM cost)
```
