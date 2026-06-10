# T-01: Setup & first delegation

**Goal:** Get mcp-coder installed and running locally, connect it to a host (Cursor), and run one `delegate_to_agent` call so you can see the full system fire end-to-end.

**After this tutorial you will have:**
- A working mcp-coder server in your Cursor `mcp.json`
- A test workspace with a minimal `.mcp-coder/config.yaml`
- One real delegation in `delegations.jsonl` you can inspect

**Estimated time:** 20–30 min on a first setup; 5 min if the repo is already installed.

**Prerequisites:** Python 3.10–3.12, an OpenRouter API key (or another LiteLLM-compatible provider). Cursor IDE.

---

## 1. Install

```bash
# Clone or open the repo (this is also the mcp-coder repo itself)
cd /path/to/mcp_coder

# Create a virtualenv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Verify
python -c "import aider; print(aider.__version__)"  # should print e.g. 0.86.2
mcp-coder --help                                     # should show subcommands
```

The installed binary is `mcp-coder`. It has three subcommands:
- *(no subcommand)* — starts the MCP stdio server (used by Cursor)
- `mcp-coder test-model` — ping your configured model; quickest sanity check
- `mcp-coder inspect-context` — dry-run the context compiler without calling Aider

---

## 2. Configure environment

Copy `.env.example` to `.env` in the repo root and fill in at minimum:

```bash
cp .env.example .env
```

The minimum required block for OpenRouter:

```bash
# .env — minimum for OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
AIDER_MODEL=openrouter/anthropic/claude-sonnet-4

# Cheap model for builder/validation/architect roles (Gemini Flash is default today)
MCP_CODER_CONTEXT_BUILDER_MODEL=openrouter/google/gemini-2.5-flash
```

> If you are **not** using OpenRouter, set `AIDER_MODEL` to any LiteLLM-compatible model id (e.g. `anthropic/claude-sonnet-4` with `ANTHROPIC_API_KEY`) — the rest of the config is provider-agnostic.

After filling `.env`, ping the model:

```bash
source .venv/bin/activate
mcp-coder test-model
# Expected: "ok" or a short completion
```

If this fails, the delegation will fail — fix API key / model id before continuing.

---

## 3. Connect to Cursor (mcp.json)

Cursor reads `~/Library/Application Support/Cursor/User/globalStorage/cursor-dev.cursor-mcp/mcp.json` on macOS, or you can use the per-project `.cursor/mcp.json`.

Add (or merge) this entry:

```json
{
  "mcpServers": {
    "mcp-coder": {
      "command": "/absolute/path/to/mcp_coder/.venv/bin/mcp-coder",
      "env": {
        "MCP_CODER_ENV_FILE": "/absolute/path/to/mcp_coder/.env"
      }
    }
  }
}
```

> Use absolute paths — Cursor may not inherit your shell `$PATH`.

**After editing `mcp.json`:** open Cursor Settings → MCP and restart the mcp-coder server (or restart Cursor). You should see `mcp-coder` listed as connected with its tools.

**What the server does on startup:**
- Reads `.env` (via `MCP_CODER_ENV_FILE` or from the working directory)
- Registers the MCP tools: `delegate_to_agent`, `inspect_context`, `list_delegations`, `get_delegation_diff`, `get_checkpoint_detail`, `get_file_history`, `rag_search`
- Syncs a Cursor rules file into the active workspace's `.cursor/rules/` if the workspace has been touched before (on first delegation, not startup)

---

## 4. Create a test workspace

For this tutorial, use any small project you own — or create a scratch directory:

```bash
mkdir ~/scratch/hello-mcp && cd ~/scratch/hello-mcp
git init
echo "# Hello" > README.md
git add . && git commit -m "init"
```

Open this folder in Cursor (File → Open Folder). You now have a workspace.

Create the workspace config:

```bash
mkdir -p .mcp-coder
cp /path/to/mcp_coder/resources/examples/config.yaml .mcp-coder/config.yaml
```

The example config is mostly commented out — the defaults are sensible. You don't need to change anything for the first run.

---

## 5. Create a minimal spec

Specs live under `.mcp-coder/specs/tasks/`. Create the folder and a first spec:

```bash
mkdir -p .mcp-coder/specs/tasks
cp /path/to/mcp_coder/resources/spec-template.md .mcp-coder/specs/tasks/hello-01.md
```

Open `.mcp-coder/specs/tasks/hello-01.md` and fill in something trivial:

```markdown
---
epic: hello
step: 1
status: open
---

## Goal
Add a one-line `hello.py` that prints "hello from mcp-coder".

## Files
### Edit
- hello.py

### Read
- README.md

## Constraints
- stdlib only; no dependencies

## Acceptance
- `python hello.py` prints exactly: hello from mcp-coder
```

---

## 6. Run the first delegation

In a **Cursor chat** (in the test workspace), the rules file should now have been synced to `.cursor/rules/use-mcp-coder.mdc` — it guides the Cursor agent on when and how to call the MCP tools.

Type something like:

```
Please implement spec tasks/hello-01.md
```

The Cursor agent (planner) should call `delegate_to_agent` with roughly:
- `task`: what the spec says
- `target_files`: `["hello.py"]`
- `context_summary`: its own summary of the conversation
- `spec_path`: `tasks/hello-01.md`
- `mode`: `implement`

You can also **call it directly** from the chat for more control:

```
Use the delegate_to_agent tool with:
- task: "Add a one-line hello.py that prints 'hello from mcp-coder'"
- target_files: ["hello.py"]
- context_summary: "Tutorial T-01 — no prior context"
- spec_path: "tasks/hello-01.md"
- mode: implement
```

---

## 7. Read the result

### Response payload

You'll get back a JSON payload. Key fields:

```json
{
  "success": true,
  "outcome": "success",
  "files_changed": ["hello.py"],
  "judgment_checklist": [...],
  "delegation_id": "xxxxxxxx-...",
  "delegation_pipeline": [
    {"phase": "spec_read", "status": "ok", "duration_ms": 3},
    {"phase": "file_picker", "status": "ok", "duration_ms": 120},
    ...
    {"phase": "executor", "status": "ok", "duration_ms": 8240},
    ...
  ]
}
```

Check:
- `success: true` and `outcome: success` — delegation applied edits and passed all checks
- `files_changed` includes `hello.py`
- `delegation_pipeline` shows all phases with `status: ok`

If `outcome: needs_input`: the executor had format errors — check `output` field for what Aider said.

### The JSONL record

Find the JSONL file:

```bash
# The project key is sha256 of the workspace path
python -c "
from core.storage.paths import session_delegations_path, workspace_pointer_path
import json, pathlib
ptr = json.loads(pathlib.Path('.mcp-coder/session.json').read_text())
print(session_delegations_path('.', ptr['mcp_session_id']))
"
# Or just find it:
find ~/.mcp-coder -name delegations.jsonl | head -5
```

Open the file and look at the last line — it's one JSON object. Notable fields:

```
delegation_id      unique id for this delegation
timestamp_start    when it started
spec_path          which spec was used
files_changed      what was actually written
outcome            success / partial / needs_input / error
context_block      what was assembled (tiers, file count, token estimate)
model_roles        which model was used for each role + tokens
delegation_pipeline phases + timing
```

This is the **canonical audit record** — everything visible in the response is derived from this.

### Verify the edit

```bash
python hello.py
# → hello from mcp-coder
```

---

## 8. What to notice

Even on this trivial delegation:

1. **`delegation_pipeline` tells you where time went** — usually `executor` dominates; `file_picker` is fast.
2. **`context_block.context_builder_llm_enabled: true`** (if default) — a builder LLM call ran before Aider. `model_roles.context_builder` in JSONL shows the model used.
3. **`model_roles.*.tokens` may be `null`** — this is a known gap (BL-335). The model ran; counting the tokens reliably is a pending fix.
4. **The spec report** was written to `.mcp-coder/specs/reports/hello-01.md` — open it to see the audit section appended by mcp-coder.
5. **`.cursor/rules/use-mcp-coder.mdc`** appeared in your workspace — this is synced from `resources/cursor-rules/` on first delegation.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: aider` | Wrong Python / venv not activated | Use absolute path to `.venv/bin/mcp-coder` in mcp.json |
| `test-model` fails with auth error | Bad API key or wrong `AIDER_MODEL` id | Check `.env`; try `curl` to the provider directly |
| `spec not found` error | spec path wrong in call | Path is relative to `.mcp-coder/specs/`; use `tasks/hello-01.md` not the full path |
| `outcome: needs_input`, output has SEARCH/REPLACE errors | Executor model format errors | Try a stronger `AIDER_MODEL`; known issue with smaller models (BL-338) |
| No JSONL file found | Session not started yet | Run one delegation first; file is created on the first write |

---

## Next

Once you have a green delegation and a JSONL record in hand:

- **T-02 (Sessions, storage, and logs):** understand the full `~/.mcp-coder` layout and what all the JSONL fields mean
- **T-04 (inspect-context):** run `mcp-coder inspect-context` on this same spec to see exactly what brief Aider received — without spending tokens
