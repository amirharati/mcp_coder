# mcp-coder resources (consumer-facing)

Assets for **other repos** that run the mcp-coder MCP server. Not loaded in this repo’s Cursor sessions (dev rules: `.cursor/rules/`).

| Path | MCP behavior |
|------|----------------|
| `spec-template.md` | Step task template → `.mcp-coder/spec-template.md` |
| `spec-epic-template.md` | Epic template → `.mcp-coder/spec-epic-template.md` |
| `spec-report-template.md` | Report template (MCP creates `specs/reports/*.md` from this) |
| `cursor-rules/` | Synced to `<workspace>/.cursor/rules/use-mcp-coder.mdc` per policy on MCP startup |
| `examples/mcp.json` | **Copy once** → `<consumer>/.cursor/mcp.json` (see `examples/MCP_SETUP.md`) — required before MCP can run |
| `examples/config.yaml` | **Reference only** — user copies to `<workspace>/.mcp-coder/config.yaml` (not auto-synced) |

Edit managed assets here; restart MCP in a consumer workspace to apply updates (rules) or rely on bootstrap (spec template on first delegate).
