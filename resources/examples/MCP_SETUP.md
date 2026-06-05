# Cursor MCP setup (consumer repo)

**One-time** — MCP cannot create this file for you (Cursor needs `mcp.json` before the server starts).

## Steps

1. Clone or open your **consumer** project in Cursor (the repo Aider should edit).
2. Copy this template:

   ```bash
   mkdir -p .cursor
   cp /PATH/TO/mcp_coder/resources/examples/mcp.json .cursor/mcp.json
   ```

3. Edit `.cursor/mcp.json` — replace every `/PATH/TO/mcp_coder` with the absolute path to your mcp-coder install.
4. Ensure `mcp_coder/.env` exists (`cp .env.example .env`, set `OPENROUTER_API_KEY`, optional `AIDER_MODEL`).
5. **Restart Cursor** (or Settings → MCP → restart servers).

## What each field does

| Field | Value |
|-------|--------|
| `command` | mcp-coder’s venv Python (not the consumer repo’s venv) |
| `args` | `main.py --mcp` in the mcp-coder repo |
| `cwd` | `${workspaceFolder}` — the **consumer** repo (opened folder) |
| `envFile` | Optional; points at mcp-coder `.env` so keys stay out of the consumer repo |

## After connect

On MCP startup, mcp-coder bootstraps in the consumer repo:

- `.cursor/rules/use-mcp-coder.mdc` (from `resources/cursor-rules/`)
- `.mcp-coder/spec-template.md` + `specs/tasks/`

Copy `resources/examples/config.yaml` → `.mcp-coder/config.yaml` when you want session policy / transcript / rule policy.

## Inline env (alternative to envFile)

```json
"env": {
  "OPENROUTER_API_KEY": "sk-or-...",
  "AIDER_MODEL": "openrouter/qwen/qwen-2.5-coder-32b-instruct"
}
```

Prefer `envFile` when the mcp-coder checkout already has `.env`.
