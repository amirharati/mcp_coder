# mcp-coder

An MCP server (with optional CLI) that wraps CLI coding agents (like Aider, OpenCode, Claude Code, etc.) and exposes them as MCP tools — with cross-session persistent context memory.

## Core Idea

Most AI coding agents are stateless per-invocation. Each conversation starts fresh. `mcp-coder` bridges this gap: it manages context across sessions so agents can remember past work, learn from previous sessions, and build on prior decisions.

The calling agent (Cursor, Claude Desktop, any MCP host) stays lean — it delegates actual code editing to the CLI agent via MCP, and `mcp-coder` handles memory, routing, and context management in between.

## Architecture

```
You (human)
  └── MCP Host (Cursor / Claude Desktop / etc.)
       └── mcp-coder (orchestrator + memory)
            ├── Router LLM (cheap model, decides what to do)
            ├── Context Janitor (cheap model, checks/freshens context)
            ├── RAG Memory (persistent, cross-session)
            ├── CLI Coder (cheap model, simple tasks)
            └── CLI Coder (expensive model, complex tasks)
```

Each sub-agent is an independent process — spawn, do one thing, return, die. No complex agent framework, just rules + model routing.

## Key Concepts

### 1. Session Management
Each `delegate_task` call starts or continues a session. Sessions can be long-lived and span multiple turns. The wrapper owns session state, not the CLI agent.

### 2. Three Context Sources
Every task fed to the CLI agent is compiled from:
- **System prompt** — fixed (project conventions, style, rules)
- **RAG context** — injected (relevant summaries from past sessions)
- **Rolling window** — last N tokens of current session history

### 3. Cross-Session Memory (RAG)
Past sessions are indexed by summary + keywords (optionally embeddings). On each new task, the router LLM searches for relevant past work and injects it into context. The coding agent can also query the RAG store mid-task via a dedicated tool.

### 4. Cheap Orchestrator, Expensive Executor
A cheap LLM (GPT-4o-mini, Gemini Flash) handles routing, context audit, RAG search, and task decomposition. The expensive LLM (Claude, GPT-5) only runs the actual coding task — focused, efficient, worth the cost.

### 5. Context Freshness
Before passing context to the expensive model, the router LLM can audit: "Is this still accurate? Are we missing anything?" If stale, it spawns a cheap sub-agent to refresh before the main task runs.

### 6. Multi-Model Ensemble (Future)
For a given task, spawn N cheap model instances with varied prompts, then consolidate results — can potentially beat a single strong model at lower cost.

### 7. Sub-Agent Toolkit
Specialized one-shot agents that can be composed:
- Critic / Code Reviewer / Security Scanner
- Test Writer / Documenter / Pattern Extractor
- Each is a cheap model call with a focused system prompt

### 8. Skills Injection
Detect topic from task, inject relevant skill files (React, Docker, testing patterns, etc.) from a skill library.

## MCP Tools

```json
{
  "delegate_task": {
    "params": {
      "task": "add pagination to /users endpoint",
      "model": "claude-sonnet-4",       // optional, default from config
      "files": ["routes/users.ts"],      // optional, specific files
      "session_id": "sess_001"           // optional, null = new session
    },
    "returns": {
      "diff": "...",                     // git diff of changes
      "summary": "...",                  // plain text summary
      "session_id": "sess_001",          // for continuation
      "files_changed": ["routes/users.ts"]
    }
  },
  "continue_session": {
    "params": {
      "session_id": "sess_001",
      "message": "now add sorting too"
    },
    "returns": { /* same as delegate_task */ }
  },
  "get_session_status": {
    "params": { "session_id": "sess_001" },
    "returns": {
      "turns": 3,
      "tokens_used": 15000,
      "files_changed": ["..."],
      "summaries": ["added pagination", "added sorting"]
    }
  },
  "rag_search": {
    "params": { "query": "pagination params" },
    "returns": {
      "results": [
        { "session_id": "sess_001", "turn": 2, "summary": "added page/limit query params" }
      ]
    }
  }
}
```

## CLI Equivalent (same backend)

```
mcp-coder --model claude "add pagination to /users" files/routes/users.ts
mcp-coder --session sess_001 "now add sorting"
mcp-coder status sess_001
mcp-coder rag "pagination params"
```

## Why This Exists

No existing tool provides clean cross-session/project memory for coding agents. Cursor, Claude Code, Aider, Windsurf — all are session-stateless. Users hack around it with AGENTS.md, CHANGELOG.md, and manual context files. `mcp-coder` makes memory a first-class layer, automatically managed, accessible via MCP to any host agent.

## Backends Supported

Any CLI coding agent with non-interactive mode:
- **Aider** (primary target) — `--yes --no-auto-commits --message "task"`
- OpenCode — `--headless` mode
- Claude Code — `--print` / `-p`
- Codex CLI — `exec` subcommand
- Gemini CLI, Goose, etc.

## Design Principles

- **Keep it simple** — no complex agent frameworks, just rules + process spawning
- **Pay for value** — cheap model for routing/memory, expensive model for actual coding
- **Session-owned state** — the wrapper owns session memory, not the CLI agent
- **Composable sub-agents** — each does one thing and dies
- **Transparent** — context is inspectable, sessions are resumable
