# T-01: Setup & first delegation

**Goal:** Get mcp-coder installed and running locally, connect it to a host (Cursor), and run one delegation so you can see the full system fire end-to-end.

**The mental model for this tutorial (read first):**
- **You** do setup once: install, configure credentials, wire it into Cursor.
- After that, **the planner (Cursor agent) drives** — guided by the rules mcp-coder syncs into your workspace, it authors the spec and calls `delegate_to_agent`. You normally do **not** hand-write spec files; that's the whole point of the workflow. (See §5.)
- In this tutorial we deliberately slow down and **inspect** what the planner and mcp-coder produce, rather than just letting it run.

**After this tutorial you will have:**
- A working mcp-coder server in your Cursor `mcp.json`
- A test workspace where mcp-coder has auto-created `.mcp-coder/` and synced its rules
- One real delegation in `delegations.jsonl`, with a spec the *planner* wrote, that you can inspect

**Estimated time:** 20–30 min on a first setup; 5 min if the repo is already installed.

**Prerequisites:** Python 3.10–3.12, an OpenRouter API key (or another LiteLLM-compatible provider). Cursor IDE.

> **Heads-up on current rough edges (being tracked).** Setup today is manual and per-machine — there is **no `mcp-coder setup` command** and **no global config UI** yet. A single `.env` *can* serve every workspace (see §2), but you still wire `mcp.json` by hand. Tracked as **BL-341** (installer + global env) and **BL-342** (`test-model` multi-model). These will smooth out; for now the manual steps below are the real path.

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

## 2. Configure environment (once, not per project)

Credentials and model ids live in a `.env` file. **You do not need one per workspace.** mcp-coder's `load_env_files()` looks in this order:

1. `MCP_CODER_ENV_FILE` — an explicit path (what you'll point `mcp.json` at below)
2. `.env` in the process working directory
3. **`.env` in the mcp-coder repo root** (next to `pyproject.toml`)

So the simplest setup is **one `.env` in the mcp-coder repo root** that serves every workspace. (A cleaner global-config story is coming — BL-341.)

```bash
cd /path/to/mcp_coder
cp .env.example .env
```

Minimum block for OpenRouter:

```bash
# .env — minimum for OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
AIDER_MODEL=openrouter/anthropic/claude-sonnet-4

# Per-role model for context_builder / spec_validation / architect roles
# (this is a separate role from the executor — see §6 of how-it-works.md)
MCP_CODER_CONTEXT_BUILDER_MODEL=openrouter/google/gemini-2.5-flash
```

> If you are **not** using OpenRouter, set `AIDER_MODEL` to any LiteLLM-compatible id (e.g. `anthropic/claude-sonnet-4` with `ANTHROPIC_API_KEY`) — the rest is provider-agnostic.

Ping the executor model to confirm credentials:

```bash
source .venv/bin/activate
mcp-coder test-model            # pings AIDER_MODEL
mcp-coder test-model --model openrouter/google/gemini-2.5-flash   # check another role's model
# Expected: "ok" or a short completion
```

> `test-model` currently pings **one** model per invocation. If you've set different models per role, ping each with `--model` for now. A list/select or `--all` table is tracked as **BL-342**.

If this fails, the delegation will fail — fix the API key / model id before continuing.

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

**What the server does on startup** (in `main.py`, every time Cursor launches it for a workspace):
- Reads `.env` (via `MCP_CODER_ENV_FILE`, then cwd, then mcp-coder repo root)
- Ensures `~/.mcp-coder/` exists (the home store)
- **Auto-creates the workspace spec layout** — `.mcp-coder/specs/{tasks,epics,reports}/` + bundled templates (`ensure_workspace_spec_layout`). Never overwrites existing files.
- **Auto-syncs the planner rules** into `.cursor/rules/` (`sync_workspace_cursor_rules`) — compiled from the bundled sources for the active policy (see §4.5)
- Registers the MCP tools: `delegate_to_agent`, `inspect_context`, `list_delegations`, `get_delegation_diff`, `get_checkpoint_detail`, `get_file_history`, `rag_search`

So you do **not** hand-create `.mcp-coder/` or copy templates — opening the workspace in Cursor (which launches the server) does it for you.

---

## 4. Open a test workspace (setup is automatic)

Use any small project you own, or create a scratch one:

```bash
mkdir ~/scratch/hello-mcp && cd ~/scratch/hello-mcp
git init
echo "# Hello" > README.md
git add . && git commit -m "init"
```

Open this folder in Cursor (File → Open Folder). Cursor launches the mcp-coder server for it, and on startup the server **creates the scaffolding for you**. After opening, look:

```bash
ls -R .mcp-coder
# .mcp-coder/spec-template.md
# .mcp-coder/specs/tasks/   .mcp-coder/specs/epics/   .mcp-coder/specs/reports/
# (+ spec-epic / spec-report templates)

ls .cursor/rules
# use-mcp-coder.mdc   workspace-history.mdc   ← synced planner rules
```

You did not create any of that. The only file mcp-coder will **never** auto-create is `.mcp-coder/config.yaml` — it's **yours** (see §4.5). Defaults apply without it.

---

## 4.5. Understand config and rules (the important part)

This is the part worth slowing down on — it's what makes the workflow tick.

### Config: `.mcp-coder/config.yaml`

- **User-owned.** mcp-coder reads it but never writes it. Optional — sensible defaults apply if absent.
- **Precedence for every flag: built-in default → env var → `config.yaml`** (yaml wins, so a repo can pin behavior regardless of your shell env).
- Start from the annotated example to see every available key:

```bash
cp /path/to/mcp_coder/resources/examples/config.yaml .mcp-coder/config.yaml
```

The keys you'll care about first (all optional):

| Key | Default | What it controls |
|-----|---------|------------------|
| `session_policy` | `always_new` | `always_new` vs `align_host` (reuse one mcp session per Cursor chat) |
| `context_builder` | on | rules-based file picker + repo map |
| `context_builder_llm` | on | the narrative builder brief (a helper-LLM call before the executor) |
| `cursor_rules_policy` | `default` | **`default` vs `strict`** rule content (see below) |
| `host_transcript` | `none` | `dump` to give helper LLMs a tail of the chat |
| `spec_validation` / `architect_pass` / `auto_verify` | off | opt-in pipeline stages (later tutorials) |

For the first run, **change nothing** — defaults are what we want to observe.

### Rules: what gets synced and why

mcp-coder syncs **planner guidance** into `.cursor/rules/` so the Cursor agent knows *how to use the MCP tools*. Two managed files:

- **`use-mcp-coder.mdc`** — the main rule: when to call `delegate_to_agent`, how to split planner vs executor work, **how to author and version specs**, and the post-delegate judgment loop.
- **`workspace-history.mdc`** — the judgment loop the planner must follow after an implement (diff → compare → pytest → done).

**Default vs strict policy** (`cursor_rules_policy`):
- **`default`** — guidance + recommendations; the planner has latitude.
- **`strict`** — same workflow, tighter mandatory phrasing (e.g. always version specs, don't verify by re-reading source when `judgment_checklist` is present). Use when you want the planner held closely to the workflow.
- Switching policy = set `cursor_rules_policy: strict` in `config.yaml`, then **restart the MCP server** (rules sync on startup). The destination file is always `use-mcp-coder.mdc` — only its content swaps.

**How rules are compiled (good to know):** the bundled sources live in `resources/cursor-rules/` and share common text via `<!-- @include use-mcp-coder.shared.md -->` directives. At sync time `_resolve_includes()` inlines the shared fragment so the workspace receives **one self-contained file** — no include markers. A `manifest.yaml` maps which source file → which destination per policy. (This is Cursor-specific today; the compile engine is host-neutral — BL-332.)

> Want to see the difference yourself: open `.cursor/rules/use-mcp-coder.mdc`, then set `cursor_rules_policy: strict`, restart the server, and re-open it. That diff is a good 2-minute experiment.

---

## 5. Let the planner author the spec (don't hand-write it)

**This is the core of the workflow.** In normal use you do **not** create spec files by hand — you describe the task to the Cursor agent, and the agent (following the synced rules) writes the epic/step spec under `.mcp-coder/specs/tasks/` and then delegates. Hand-authoring specs would defeat the entire point of building this workflow layer.

In a **Cursor chat** in your test workspace, say something like:

```
Using mcp-coder, implement a one-line hello.py that prints exactly
"hello from mcp-coder". Stdlib only. Write the spec first, then delegate.
```

Guided by `use-mcp-coder.mdc`, the agent should:
1. Create a versioned step spec, e.g. `.mcp-coder/specs/tasks/hello-01-v1.md`, with `## Goal / ## Files (Edit/Read) / ## Constraints / ## Acceptance`.
2. Call `delegate_to_agent` with `spec_path: tasks/hello-01-v1.md`, `target_files: ["hello.py"]`, `mode: implement`, and a `context_summary`.

**Now inspect what it wrote — this is the learning moment.** Open the generated spec and read it critically:

- Is the `## Goal` a single clear outcome?
- Does `## Files → ### Edit` list exactly `hello.py`? Anything in `### Read`?
- Are `## Constraints` (stdlib only) captured?
- Is `## Acceptance` checkable (the exact printed string)?

This is where your attention belongs in the workflow: **the quality of the spec the planner produces**, not typing it yourself. If the spec is vague, that's a planner-guidance (rules) observation worth noting — not something to fix by editing the file by hand.

> **Want to go one step at a time?** Today the planner tends to author-and-delegate in one go. You can force a slower loop by telling it to **stop after writing the spec** so you can review, or by asking for `mode=review` first (questions only, no edits). A first-class "pause between steps / always review" switch isn't built yet — tracked as **P4.5-ISS-004**. For now, instruct the agent explicitly.

---

## 6. What the delegation call looks like

When the planner delegates (from §5), under the hood it's one `delegate_to_agent` call, roughly:

- `task`: the goal, in the planner's words
- `target_files`: `["hello.py"]` (edit paths; read-deps are auto-merged from the spec)
- `context_summary`: the planner's summary of the conversation — the executor can't see the chat
- `spec_path`: `tasks/hello-01-v1.md`
- `mode`: `implement`

You normally don't type this — the planner builds it from the spec and the rules. It's shown here so you recognize the arguments in the JSONL record (§7). If you ever want to drive it manually for an experiment, you can ask the agent to "call `delegate_to_agent` with exactly these arguments," but that's the exception, not the workflow.

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
4. **The spec report** was written to `.mcp-coder/specs/reports/hello-01-v1.md` (same name as the spec) — open it to see the audit section appended by mcp-coder.
5. **`.cursor/rules/use-mcp-coder.mdc`** was already in your workspace before the delegation — it's synced from `resources/cursor-rules/` on **server startup** (compiled from the `default`/`strict` sources, §4.5), and it's what told the planner to write the spec the way it did.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: aider` | Wrong Python / venv not activated | Use absolute path to `.venv/bin/mcp-coder` in mcp.json |
| `test-model` fails with auth error | Bad API key or wrong `AIDER_MODEL` id | Check `.env`; try `curl` to the provider directly |
| `spec not found` error | spec path wrong in call | Path is relative to `.mcp-coder/specs/`; use `tasks/hello-01-v1.md` not the full path |
| `outcome: needs_input`, output has SEARCH/REPLACE errors | Executor model format errors | Try a stronger `AIDER_MODEL`; known issue with smaller models (BL-338) |
| No JSONL file found | Session not started yet | Run one delegation first; file is created on the first write |

---

## Next

Once you have a green delegation and a JSONL record in hand:

- **T-02 (Sessions, storage, and logs):** understand the full `~/.mcp-coder` layout and what all the JSONL fields mean
- **T-04 (inspect-context):** run `mcp-coder inspect-context` on this same spec to see exactly what brief Aider received — without spending tokens
