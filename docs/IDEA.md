# mcp-coder

An MCP server (with optional CLI) that wraps CLI coding agents (like Aider, OpenCode, Claude Code, etc.) and exposes them as MCP tools — with cross-session persistent context memory.

## Core Idea & Vision

Most AI coding agents (Cursor, Claude Code, Aider, Windsurf) are stateless per-invocation or per-session. Each conversation starts fresh. Users hack around this "Context Amnesia" using `MEMORY.md`, `CHANGELOG.md`, and manual context files. 

`mcp-coder` bridges this gap. It acts as a **Task-Level Orchestrator and Memory Bank**. 

The calling agent (e.g., Cursor, Claude Desktop) stays lean, acting as a thin orchestration and UI layer. When a complex, multi-file task is needed, Cursor delegates the actual code editing to `mcp-coder` via MCP. `mcp-coder` then handles task scoping, memory retrieval, routing, and launches a dedicated CLI agent (like OpenCode or Aider) to execute the work.

### The Two-Tiered Optimization Architecture

This project is designed to work in tandem with a separate, lower-level proxy (like `context_optimizer_proxy`), creating a two-tiered optimization system:

1. **Tier 1: Task-Level Optimization (`mcp-coder`)**
   - **Scope:** Coarse-grained, once per task.
   - **Role:** The "Brain" and Session Manager.
   - **Action:** Receives a high-level goal from Cursor. Checks past session memory ("Have we done this before?"). Decides which files are relevant. Launches the CLI agent (OpenCode/Aider) as a subprocess with a tightly scoped context.
   - **Why:** Massive token savings and better execution quality by preventing the agent from wandering through the whole repo. Safe, because it doesn't interfere with the agent's internal loop.

2. **Tier 2: Turn-Level Optimization (`context_optimizer_proxy` - *Separate Project*)**
   - **Scope:** Fine-grained, intercepts every single LLM API call.
   - **Role:** The "Pipes" and Token Squeezer.
   - **Action:** Sits between the CLI agent and the LLM API. Strips boilerplate tool noise, compresses paths, and manages cache boundaries on every turn.
   - **Why:** Squeezes maximum efficiency out of the execution loop.

*By separating these concerns, `mcp-coder` remains a clean orchestration layer, while the proxy handles the risky, low-level prompt hacking.*

## Architecture

```
You (human)
  └── MCP Host (Cursor / Claude Desktop / etc.) -> "Thin UI Layer"
       └── mcp-coder (orchestrator + memory) -> "Task-Level Optimizer"
            ├── Router LLM (cheap model, decides what to do)
            ├── Context Janitor (cheap model, checks/freshens context)
            ├── RAG Memory (persistent, cross-session)
            └── CLI Coder (OpenCode/Aider) -> "Execution Engine"
                 └── context_optimizer_proxy -> "Turn-Level Optimizer" (Optional)
                      └── Actual LLM (Claude, GPT-4o)
```

Each sub-agent is an independent process — spawn, do one thing, return, die. No complex agent framework, just rules + model routing.

## Key Concepts

### 1. The "Cheap Orchestrator, Expensive Executor" Pattern
A cheap LLM (GPT-4o-mini, Gemini Flash) handles routing, context audit, RAG search, and deciding which files to pass to the agent. The expensive LLM (Claude 3.5 Sonnet) only runs the actual coding task inside the CLI agent — focused, efficient, worth the cost.

### 2. Session Management
Each `delegate_task` call starts or continues a session. Sessions can be long-lived and span multiple turns. The wrapper owns session state, not the CLI agent. The wrapper acts as a **session scheduler** — deciding when to start a fresh session vs. continue an existing one to keep context size manageable.

### 3. Cross-Session Memory (RAG)
Past sessions are indexed by summary + keywords (optionally embeddings). On each new task, the router LLM searches for relevant past work and injects it into context. The coding agent can also query the RAG store mid-task via dedicated tools.

### 4. Context Freshness (Context Janitor)
Before passing context to the expensive model, the router LLM can audit: "Is this still accurate? Are we missing anything?" If stale, it spawns a cheap sub-agent to refresh before the main task runs.

### 5. Context Extraction (Solving the Walled Garden)
A major challenge with MCP tools is that they do not receive the full chat history from the host IDE (like Cursor). To ensure the CLI agent has the exact nuance of the user's request without burning tokens on summaries, `mcp-coder` uses a shared-filesystem approach:
- **Primary Strategy (SpecStory):** `mcp-coder` looks for the `.specstory/history/` directory in the project root. If present, it reads the most recently modified Markdown file (which contains the real-time, perfect-fidelity transcript of the active Cursor chat) and injects it into the CLI agent's prompt.
- **Fallback Strategy:** If no local transcript is available, it relies on a `context_from_chat` parameter in the MCP tool schema, forcing the host LLM to summarize the relevant decisions before delegation.

### 6. Dual-Mode Operation (MCP + CLI)
`mcp-coder` is built to be used both as an MCP server (called by Cursor) AND as a standalone CLI tool. This allows the same powerful, memory-backed agent to be used directly in the terminal when Cursor is closed.

## Data Models

### Session Entry
```python
session_entry = {
  id: str,                    # "sess_001"
  created: timestamp,
  turns: [
    {
      turn: 1,
      task: str,              # original task from host
      model_used: str,        # e.g. "claude-sonnet-4"
      files: [str],           # files involved
      diff: str,              # raw git diff
      summary: str,           # human-readable summary
      tokens_used: int,
      timestamp: timestamp
    },
  ],
  rolling_context: str,       # last N tokens of conversation (pruned)
  total_tokens: int
}
```

### RAG Entry
```python
rag_entry = {
  session_id: str,
  turn: int,
  summary: str,               # short description
  keywords: [str],            # for keyword matching
  embedding: [float],         # from cheap LLM (optional)
  timestamp: timestamp
}
```

## MCP Tools (Example Schema)

```json
{
  "delegate_task": {
    "params": {
      "task": "add pagination to /users endpoint",
      "model": "claude-sonnet-4",
      "files_hint": ["routes/users.ts"],
      "session_id": "sess_001"
    },
    "returns": {
      "diff": "...",
      "summary": "...",
      "session_id": "sess_001",
      "files_changed": ["routes/users.ts"]
    }
  }
}
```

## CLI Equivalent (same backend)

```bash
mcp-coder --model claude "add pagination to /users" files/routes/users.ts
mcp-coder --session sess_001 "now add sorting"
mcp-coder status sess_001
mcp-coder rag "pagination params"
```

## Backends Supported

Any CLI coding agent with non-interactive mode:
- **OpenCode** (Primary target - excellent multi-LLM support and modern architecture)
- **Aider** (`--yes --no-auto-commits --message "task"`)
- Claude Code (`--print` / `-p`)

## Design Principles

- **Keep it simple** — no complex agent frameworks, just rules + process spawning.
- **Pay for value** — cheap model for routing/memory, expensive model for actual coding.
- **Session-owned state** — the wrapper owns session memory, not the CLI agent.
- **Layered Optimization** — Task-level optimization belongs here; turn-level prompt hacking belongs in a proxy.
- **Transparent** — context is inspectable, sessions are resumable.