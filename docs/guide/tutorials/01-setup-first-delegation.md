# T-01: Setup & first delegation

**Goal:** Get mcp-coder installed and running locally, connect it to a host (Cursor), and run one delegation so you can see the full system fire end-to-end.

**The mental model for this tutorial (read first):**
- **You** do setup once: install, configure credentials, wire it into Cursor.
- After that, **the planner (Cursor agent) drives** — guided by rules mcp-coder syncs into your workspace, it authors the spec and calls `delegate_to_agent`. You normally do **not** hand-write spec files; that's the whole point of the workflow. (See §5.)
- In this tutorial we deliberately slow down and **inspect** what the planner and mcp-coder produce, rather than just letting it run.

**After this tutorial you will have:**
- `mcp-coder` available globally on your machine
- A test workspace where mcp-coder has auto-created `.mcp-coder/` and synced its rules
- One real delegation in `delegations.jsonl`, with a spec the *planner* wrote, that you can inspect

**Estimated time:** 10–15 min on a first install; 5 min for subsequent workspaces.

**Prerequisites:** Python 3.10–3.12, an OpenRouter API key (or another LiteLLM-compatible provider). Cursor IDE.

---

## 1. Install

Clone the repo, then run the install script:

```bash
git clone <repo-url> mcp_coder
cd mcp_coder
./install.sh
```

`install.sh` does three things:
1. Creates `.venv/` and runs `pip install -e .` if the venv doesn't exist yet
2. Writes a wrapper at `/usr/local/bin/mcp-coder` that points back to this repo's venv
3. Prints a short "Try it" hint

After it finishes, `mcp-coder` is available from any directory. Verify:

```bash
mcp-coder --help          # shows subcommands
mcp-coder setup           # shows workspace + model info (see §3)
```

> **Running `mcp-coder` bare in the terminal** shows help and exits — the MCP stdio server only starts when launched by Cursor (piped stdin) or `mcp-coder --mcp`. This is intentional so a stray terminal invocation doesn't hang.

**CLI subcommands at a glance:**

| Subcommand | What it does |
|-----------|-------------|
| `mcp-coder setup` | Print workspace info + the exact `mcp.json` block to paste |
| `mcp-coder test-model` | Ping one model; `--all` tests every configured role |
| `mcp-coder inspect-context` | Dry-run the context compiler — no backend call |
| `mcp-coder history` | Browse `workspace_history.db` |
| `mcp-coder rag` | Search the delegation FTS5 index |

---

## 2. Configure environment (once, not per project)

Credentials and model ids live in a `.env` file. **You only need one** — it lives in the mcp-coder repo root and serves every workspace. `load_env_files()` resolution order:

1. `MCP_CODER_ENV_FILE` — explicit path set in `mcp.json` env block (see §3)
2. `.env` in the process working directory
3. **`.env` in the mcp-coder repo root** ← this is the "global" env

```bash
cd /path/to/mcp_coder
cp .env.example .env
# Fill in your keys
```

Minimum for OpenRouter:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
AIDER_MODEL=openrouter/anthropic/claude-sonnet-4

# Per-role model for context_builder / spec_validation / architect
MCP_CODER_CONTEXT_BUILDER_MODEL=openrouter/google/gemini-2.5-flash
```

> For other providers (Anthropic direct, OpenAI, etc.) set `AIDER_MODEL` to any LiteLLM-compatible id and the matching `*_API_KEY` — everything else is provider-agnostic.

---

## 3. Connect to Cursor (`mcp.json`)

Wire mcp-coder into Cursor with one command:

```bash
# Wire this project only (writes/merges .cursor/mcp.json in cwd)
mcp-coder setup --local

# Wire all Cursor projects at once (writes/merges Cursor's global mcp.json)
mcp-coder setup --global
```

Both commands merge the `mcp-coder` entry — any other MCP servers already in the file are untouched. Re-running is safe (updates the existing entry). Creates the file and parent directories if they don't exist yet.

**Not sure which to use?** Run `mcp-coder setup` (no flags) first — prints a dry-run of what would be written plus a prompt:

```
→  Run 'mcp-coder setup --local' to wire this project, or '--global' for all Cursor projects.
```

| Option | What it writes | When to use |
|--------|---------------|-------------|
| `--global` | System-wide Cursor `mcp.json` | Regular use — one command, all projects |
| `--local` | `.cursor/mcp.json` in cwd | Dev/selective — this project only |

> **Both options are fully isolated per project.** The server's `cwd` is the workspace root either way, so each project gets its own `.mcp-coder/` specs/config and its own `~/.mcp-coder/projects/<id>/` history. Global does not mean shared state.

After running either command, open **Cursor Settings → MCP** and restart the mcp-coder entry. You should see it listed as connected.

**What the server does on first startup for a workspace:**
- Auto-creates `.mcp-coder/specs/{tasks,epics,reports}/` + bundled spec templates
- Compiles and syncs `.cursor/rules/use-mcp-coder.mdc` + `workspace-history.mdc`
- Registers the MCP tools for that workspace session

---

## 4. Verify models

Ping all configured role models to confirm credentials:

```bash
mcp-coder test-model --all
```

Expected output:

```
executor         openrouter/anthropic/claude-sonnet-4   OK  latency=1240ms
context_builder  openrouter/google/gemini-2.5-flash     OK  latency=680ms
review           openrouter/anthropic/claude-sonnet-4   OK  latency=1190ms  (fallback from executor)

All 3 passed.
```

If any role fails, fix the API key / model id before continuing — a failing executor means every delegation fails; a failing `context_builder` means the builder brief is silently skipped.

---

## 5. Open a test workspace (scaffolding is automatic)

Use any small project you own, or create a scratch one:

```bash
mkdir ~/scratch/hello-mcp && cd ~/scratch/hello-mcp
git init
echo "# Hello" > README.md
git add . && git commit -m "init"
```

How you wire this project depends on what you ran in §3:

**If you used `setup --global`** — open the folder in Cursor. The server starts automatically for every project; no extra step in this directory.

**If you used `setup --local` only (or skipped global on purpose)** — wire *this* project before opening it in Cursor:

```bash
cd ~/scratch/hello-mcp
mcp-coder setup --local
```

Then open the folder in Cursor. mcp-coder runs only for projects that have `.cursor/mcp.json` (or wherever you pointed global config).

Either way, once the server has started for this workspace it **creates the scaffolding on first startup**:

```
.mcp-coder/
  spec-template.md          ← task spec template
  specs/tasks/              ← where versioned step specs live
  specs/epics/              ← multi-step epic specs
  specs/reports/            ← mcp-coder appends audit here after each delegation

.cursor/rules/
  use-mcp-coder.mdc         ← planner guidance (synced, default policy)
  workspace-history.mdc     ← post-delegate judgment loop
```

Check **Cursor Settings → MCP** — mcp-coder should show as connected. If not: for global, restart Cursor after editing the system `mcp.json`; for local, confirm `.cursor/mcp.json` exists in this project and restart the MCP entry.

### Optionally create a workspace config

```bash
mcp-coder setup --init-config
# Creates .mcp-coder/config.yaml from the bundled example (never overwrites)
```

The config is mostly commented out — defaults are sensible for a first run. The one thing worth knowing now: `cursor_rules_policy: default` (the default) vs `strict` (tighter mandatory workflow phrasing). See §5.1 for the full config/rules walkthrough.

---

## 5.1 Config and rules (the important part)

### Config: `.mcp-coder/config.yaml`

- **User-owned.** mcp-coder reads it, never writes it (except `--init-config` creating it from template).
- **Precedence: built-in default → env var → `config.yaml`** — yaml wins, so a repo can pin behaviour regardless of your shell environment.

Key flags you'll encounter:

| Key | Default | Effect |
|-----|---------|--------|
| `session_policy` | `always_new` | `align_host` reuses one session per Cursor chat |
| `context_builder` | on | file picker + repo map before every delegation |
| `context_builder_llm` | on | helper LLM narrative brief on top of picker output |
| `cursor_rules_policy` | `default` | `default` vs `strict` rule content (see below) |
| `host_transcript` | off | `dump` gives helper LLMs a tail of the chat |
| `spec_validation` / `architect_pass` / `auto_verify` | off | opt-in pipeline stages |

### Rules: what gets synced and why

mcp-coder syncs **planner guidance** into `.cursor/rules/` so the Cursor agent knows how to use the tools:

- **`use-mcp-coder.mdc`** — when to delegate, how to write and version specs, what `target_files` to pass, post-delegate judgment loop.
- **`workspace-history.mdc`** — the mandatory judgment loop the planner follows after an implement delegation.

**Default vs strict:** `strict` uses tighter mandatory phrasing (always version specs, don't verify by re-reading source when `judgment_checklist` is present). Switch by setting `cursor_rules_policy: strict` in `config.yaml`, then **restart the MCP server**.

**How rules are compiled:** bundled sources in `resources/cursor-rules/` share sections via `<!-- @include use-mcp-coder.shared.md -->`. At sync time `_resolve_includes()` inlines the shared fragment — the workspace receives one self-contained `.mdc` file. `manifest.yaml` controls which source maps to which destination per policy.

---

## 6. Let the planner author the spec

In a Cursor chat in the test workspace, describe the task:

```
Using mcp-coder, implement a one-line hello.py that prints exactly
"hello from mcp-coder". Stdlib only. Write the spec first, then delegate.
```

Guided by `use-mcp-coder.mdc`, the agent should:
1. Create a versioned step spec, e.g. `.mcp-coder/specs/tasks/hello-01-v1.md`
2. Call `delegate_to_agent` with `spec_path`, `target_files`, `mode: implement`, and `context_summary`

**Inspect what the planner wrote before the delegation runs.** Open the generated spec and ask:
- Is `## Goal` a single clear outcome?
- Does `## Files → ### Edit` list exactly `hello.py`?
- Are `## Constraints` (stdlib only) captured?
- Is `## Acceptance` checkable (the exact printed string)?

**This inspection is the learning moment** — not typing the spec yourself. If the spec is vague, that's a planner-guidance (rules) observation, not something to fix by hand-editing. If you want to slow down and review before the delegation fires, tell the agent: *"stop after writing the spec, I'll tell you when to delegate."*

---

## 7. What the delegation call looks like

When the planner delegates, it's one `delegate_to_agent` call:

- `task`: goal in the planner's words
- `target_files`: `["hello.py"]` (edit paths; read-deps are auto-merged from the spec)
- `context_summary`: planner's summary — the executor can't see the chat
- `spec_path`: `tasks/hello-01-v1.md`
- `mode`: `implement`

You normally don't type this — it's shown here so you recognise the arguments in the JSONL record (§8).

---

## 8. Read the result

### Response payload

The response is a JSON object. Key fields:

```json
{
  "success": true,
  "outcome": "success",
  "files_changed": ["hello.py"],
  "judgment_checklist": [...],
  "delegation_id": "xxxxxxxx-...",
  "delegation_pipeline": [
    {"phase": "spec_read",    "status": "ok", "duration_ms": 3},
    {"phase": "file_picker",  "status": "ok", "duration_ms": 120},
    {"phase": "builder_llm",  "status": "ok", "duration_ms": 980},
    {"phase": "executor",     "status": "ok", "duration_ms": 8240},
    {"phase": "post_gateway", "status": "ok", "duration_ms": 15}
  ]
}
```

- `success: true` + `outcome: success` — edits applied, scope gateway passed
- `files_changed` contains `hello.py`
- `delegation_pipeline` shows every phase with timing

If `outcome: needs_input`: the executor had format errors — check `output` field.

### The JSONL record

Find it:

```bash
find ~/.mcp-coder -name delegations.jsonl | head -5
# then: tail -1 <path> | python -m json.tool | head -60
```

The last line is the full audit record for the delegation. Notable top-level fields: `delegation_id`, `timestamp_start`, `spec_path`, `files_changed`, `outcome`, `context_block` (what was assembled), `model_roles` (which model ran per role + tokens + cost), `delegation_pipeline`.

### Verify the edit

```bash
python hello.py
# → hello from mcp-coder
```

---

## 9. What to notice

Even on this trivial delegation:

1. **`delegation_pipeline` shows where time went.** `executor` typically dominates. `file_picker` and `context_assemble` are fast. `builder_llm` adds ~500–1500ms for the narrative brief.
2. **`model_roles.context_builder`** in JSONL — the builder brief ran on a separate model role before the executor. This is configurable or can be disabled with `context_builder_llm: false`.
3. **`model_roles.*.tokens` may be `null`** — known gap (BL-335). The model ran; token counting is a pending fix.
4. **The spec report** at `.mcp-coder/specs/reports/hello-01-v1.md` — mcp-coder appended an audit section. Open it to see what was recorded.
5. **`use-mcp-coder.mdc`** was in `.cursor/rules/` before the delegation ran — it was compiled and synced on server startup, and it's what told the planner how to write the spec.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `mcp-coder: command not found` | `install.sh` not run, or `/usr/local/bin` not in `PATH` | Re-run `./install.sh`; check `echo $PATH` |
| `mcp-coder setup` shows `Env file: (not found)` | `.env` not found in repo root or cwd | Create `.mcp-coder/.env` in the repo or set `MCP_CODER_ENV_FILE` in `mcp.json` |
| `test-model --all` shows `FAIL` on a role | Bad key or wrong model id | Fix in `.env`; run `mcp-coder setup` again to see resolved models |
| `spec not found` error during delegation | Spec path wrong | Path is relative to `.mcp-coder/specs/`; planner should use `tasks/hello-01-v1.md` |
| `outcome: needs_input`, SEARCH/REPLACE errors | Executor model format errors — common on smaller models | Try a stronger `AIDER_MODEL` (BL-338) |
| No JSONL file | No delegation has run yet | Run a delegation first |

---

## Next

- **T-02 (Sessions, storage, and logs):** understand the full `~/.mcp-coder` layout and what every JSONL field means
- **T-04 (inspect-context):** run `mcp-coder inspect-context` on this spec to see exactly what brief the executor received — without spending tokens
