# mcp-coder

MCP server that delegates coding work to CLI agents (Aider, OpenCode, …) with pass-through context and structured delegation logs.

**Phase 1 progress:** MCP → Aider delegation, home storage, Cursor host linking, session policies, opt-in transcript dump, **spec workflow** (epic/step specs, `mode=review|implement`, reports). Exit review: [docs/PHASE1_MVP.md](docs/PHASE1_MVP.md) P1-199.

**Docs:** [docs/README.md](docs/README.md) · **Vision:** [docs/IDEA.md](docs/IDEA.md) · **Doc map:** [docs/VISION_DOCS.md](docs/VISION_DOCS.md)

---

## Install

**Full guide:** [docs/INSTALL.md](docs/INSTALL.md) (prerequisites, locked vs flexible install, lock regeneration).

Requires **Python 3.10–3.12** (`aider-chat` does not support 3.13+). Use **3.12** if you can (see `.python-version`).

### Reproducible (recommended)

```bash
cd /path/to/mcp_coder
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh --locked --dev   # venv + pinned deps + pytest
make test                               # optional shorthand
```

Uses `requirements-lock.txt` (pinned transitive tree) plus editable `mcp-coder`.

### Flexible (latest within pyproject ranges)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install -e ".[dev]"
pytest
```

### What you need installed

| Component | Package / tool |
|-----------|----------------|
| Python | 3.10–3.12 |
| git | system `git` |
| MCP server | `mcp` (via pip) |
| Aider engine | `aider-chat` (via pip) |
| This project | `pip install -e .` |
| Tests (optional) | `pytest` (`[dev]` or `requirements-dev.txt`) |
| Real delegations | `OPENROUTER_API_KEY` (default provider) |

### Do you need a `.env` file?

| What you're doing | API keys / `.env` |
|-------------------|-------------------|
| Install, `pytest`, MCP server starts | **Not needed** |
| `delegate_to_agent` actually calls the LLM | **Yes** — provider key for your model |

**Three ways to supply keys** (pick one):

1. **`.env` in the workspace** Cursor uses as MCP `cwd` (recommended for local dev):
   ```bash
   cp .env.example .env   # in mcp_coder repo, or copy fields into your project's .env
   # edit .env — never commit it
   ```
   On startup, `main.py` loads `.env` from `cwd` (and from the mcp-coder repo root as fallback). `python-dotenv` comes in via `aider-chat`.

2. **Cursor `mcp.json` `env` block** — good when you do not want a file in the target repo:
   ```json
   "env": {
     "OPENROUTER_API_KEY": "sk-or-...",
     "OPENROUTER_API_BASE": "https://openrouter.ai/api/v1",
     "AIDER_MODEL": "openrouter/openai/gpt-4o-mini"
   }
   ```

3. **Shell exports** before starting Cursor:
   ```bash
   export OPENROUTER_API_KEY=sk-or-...
   export AIDER_MODEL=openrouter/openai/gpt-4o-mini
   ```

Template: [`.env.example`](.env.example). See [docs/INSTALL.md](docs/INSTALL.md) for troubleshooting.

### Model (OpenRouter default)

Phase 1 uses **one model at a time**, set in `.env`:

| Variable | Purpose |
|----------|---------|
| `AIDER_MODEL` | Model id for Aider (preferred) |
| `MCP_CODER_MODEL` | Alias if `AIDER_MODEL` is unset |

**Default** (if neither is set): `openrouter/openai/gpt-4o-mini` — cheap, fine for dev.

**Serious testing** — change only `AIDER_MODEL` in `.env`, e.g.:

```bash
AIDER_MODEL=openrouter/anthropic/claude-sonnet-4
```

Other providers (Anthropic, OpenAI direct) still work if you set the matching API key and an appropriate `AIDER_MODEL` id. See [Aider OpenRouter docs](https://aider.chat/docs/llms/openrouter.html).

**Test model** (same `.env` / LiteLLM path as delegations, no Aider edit loop):

```bash
source .venv/bin/activate
mcp-coder test-model
mcp-coder test-model --model openrouter/anthropic/claude-sonnet-4
mcp-coder test-model --via litellm   # raw LiteLLM only (compare when debugging)
mcp-coder test-model --via both      # Aider Model + LiteLLM
```

Prints config resolution (env files, model source, API base, key masked) on stderr, then pings via **Aider `Model`** by default — same stack as `delegate_to_agent`. Exit `0` = `OK` + reply; exit `1` = provider error (run before a long E2E).

---

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENROUTER_API_KEY` | — | **Required** for default OpenRouter models |
| `OPENROUTER_API_BASE` | `https://openrouter.ai/api/v1` | OpenRouter API URL (LiteLLM/Aider) |
| `MCP_CODER_OPENROUTER_API_BASE` | (same as default) | Alias if `OPENROUTER_API_BASE` unset |
| `AIDER_MODEL` | `openrouter/openai/gpt-4o-mini` | Model passed to Aider |
| `MCP_CODER_MODEL` | (same as default) | Alias when `AIDER_MODEL` unset |
| `MCP_CODER_DEFAULT_BACKEND` | `aider` | Execution adapter id (`get_engine`) |
| `MCP_CODER_SESSION_POLICY` | `always_new` | `always_new` \| `align_host` — reuse mcp session per host chat |
| `MCP_CODER_FALLBACK_SESSION` | — | **Deprecated**; use `MCP_CODER_SESSION_POLICY` |
| `MCP_CODER_HOST_TIE_WINDOW_SEC` | `10` | Host transcript scoring tie window (seconds) |
| `MCP_CODER_HOME` | `~/.mcp-coder` | Canonical store for projects, sessions, delegation logs |
| `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE` | off | Also append to `<workspace>/.mcp-coder/logs/delegations.jsonl` |
| `MCP_CODER_WORKSPACE` | process `cwd` | Repo root for git diff + project_key |
| `MCP_CODER_LOG_DIR` | — | If set, mirror `delegations.jsonl` to this directory (canonical stays home) |
| `MCP_CODER_LOG_BRIEF` | on | Brief receive/send lines on **stderr** (safe for MCP) |
| `MCP_CODER_LOG_VERBOSE` | off | Extra summary when JSONL row is appended |
| `MCP_CODER_LOG_FULL_PROMPT` | off | Include full prompt in JSONL record |
| `MCP_CODER_SERVER_LOG` | on | Append structured server audit log to JSONL (`0`/`off` disables file only) |
| `MCP_CODER_SERVER_LOG_LEVEL` | `info` | `error` \| `warn` \| `info` \| `debug` — minimum level for file append |
| `MCP_CODER_SERVER_LOG_SCOPE` | `global` | `global` \| `project` \| `both` — where `server.jsonl` is written |

```bash
MCP_CODER_HOME=~/.mcp-coder
MCP_CODER_SESSION_POLICY=always_new
# MCP_CODER_SESSION_POLICY=align_host
# MCP_CODER_MIRROR_LOGS_TO_WORKSPACE=1
# MCP_CODER_LOG_VERBOSE=1
# MCP_CODER_LOG_FULL_PROMPT=1
# MCP_CODER_SERVER_LOG=1
# MCP_CODER_SERVER_LOG_LEVEL=info
# MCP_CODER_SERVER_LOG_SCOPE=global
```

**Server audit log** (`server.jsonl`): durable JSONL for MCP startup, singleton, host resolve, session acquire, and delegation lifecycle. Stderr brief lines (`MCP_CODER_LOG_BRIEF`) are unchanged. Workspace `config.yaml` keys `server_log`, `server_log_level`, and `server_log_scope` override env. Inspect with `make server-logs-last` (global) or `make server-logs-last TEST_WS=/path/to/repo` (project file). Rotation (`MCP_CODER_SERVER_LOG_MAX_MB`) is not implemented.

---

## Storage layout

Canonical delegation logs live under **`MCP_CODER_HOME`** (default `~/.mcp-coder`), not in the git repo. Session folders:

```text
~/.mcp-coder/
  server.jsonl                       # global MCP server audit log (default scope)
  projects/<project_key>/sessions/<mcp_session_id>/
  session.json
  delegations.jsonl
```

**Session policy:** default `always_new` creates a new `mcp_session_id` on every call. With `align_host` (env or `<workspace>/.mcp-coder/config.yaml`), reuse the latest mcp session for the same `(project_key, host_session_id)` and append to the same `delegations.jsonl`. In-process Aider Coder instances are cached per `mcp_session_id` until `target_files` change or MCP restarts.

`project_key` is the full SHA-256 hex of the resolved absolute workspace path. Each delegation updates `<workspace>/.mcp-coder/session.json` (system pointer). User settings live in `<workspace>/.mcp-coder/config.yaml` and are **never overwritten** by mcp-coder.

See [docs/notes/storage-and-linking.md](docs/notes/storage-and-linking.md) for IDs, link fields, and migration notes from P1-100 workspace-local logs.

---

## Host adapter (Cursor)

mcp-coder resolves **which Cursor chat is active** via a host adapter layer (`core/host/`). On each delegation it records metadata (path, ids, sizes). **Transcript injection is opt-in** — default `host_transcript: none` sends only `context_summary` + `task`; set `host_transcript: dump` to prepend the full parsed Cursor chat JSONL (dump-all, no smart trim).

| Field | Meaning |
|-------|---------|
| `host_kind` | `"cursor"` when resolved |
| `host_session_id` | Cursor transcript uuid (scored: max of transcript mtime and delegation history) |
| `host_transcript_path` | Absolute path to nested `…/<id>/<id>.jsonl` |
| `context_mode` | `fallback` (default) or `host_transcript` when dump injected text |
| `context.host_transcript_injected_bytes` | UTF-8 size of transcript block in the Aider prompt |
| `context.host_transcript_file_bytes` | Raw on-disk JSONL size (stat) |
| `context.host_transcript_bytes` | Alias of `host_transcript_injected_bytes` (one release) |

**Transcript policy** (default `none`):

| `host_transcript` | Behavior |
|-------------------|----------|
| `none` | Mode A — summary + task only; no file read |
| `dump` | Mode B — full parsed transcript prepended; may hit model context limits on long chats |

Resolution: built-in default → `MCP_CODER_HOST_TRANSCRIPT` env → `<workspace>/.mcp-coder/config.yaml` (yaml wins). Optional tail cap when dump enabled: `MCP_CODER_MAX_TRANSCRIPT_BYTES` (0/unset = no limit).

With `dump` + a very long chat, delegations **should** fail with provider context/token errors — that is expected in Phase 1. Check `host_transcript_injected_bytes` and `prompt_tokens_est` in `delegations.jsonl`. Live overflow test: `MCP_CODER_OVERFLOW_TEST=1 pytest tests/test_transcript_overflow.py -s` (needs `OPENROUTER_API_KEY`).

**Slug heuristic:** resolved workspace path → replace `/` with `-` (e.g. `/Users/amir/Code/foo` → `Users-amir-Code-foo`). If that folder is missing under `~/.cursor/projects/`, tries `_` → `-` in the slug. Override with `MCP_CODER_CURSOR_PROJECT_SLUG` if the heuristic fails.

| Env | Default | Purpose |
|-----|---------|---------|
| `MCP_CODER_HOST` | `auto` | `auto` \| `cursor` \| `none` |
| `MCP_CODER_CURSOR_ROOT` | `~/.cursor` | Cursor config root (tests override) |
| `MCP_CODER_CURSOR_PROJECT_SLUG` | — | Skip slug heuristic; use this folder name |
| `MCP_CODER_HOST_TIE_WINDOW_SEC` | `10` | Tie window for host scoring (seconds) |
| `MCP_CODER_HOST_TRANSCRIPT` | `none` | `none` \| `dump` — full Cursor chat prepend |
| `MCP_CODER_MAX_TRANSCRIPT_BYTES` | `0` | Tail cap on injected transcript when `dump` (0 = uncapped) |

**Workspace override:** `<workspace>/.mcp-coder/config.yaml` (user-owned; mcp-coder reads only):

```yaml
# Reuse mcp session per Cursor chat
session_policy: align_host

# Opt-in full transcript injection (default: none)
# host_transcript: dump
```

Wins over env. Legacy `config.json` still works if yaml is missing. Example: `resources/examples/config.yaml` (copy manually). Delegation updates `session.json` (pointer) only — not config.

When resolved, stderr may show: `[mcp-coder] host cursor session=59553f0e… transcript=…`

**Aider + MCP (Playwright):** FastMCP runs on asyncio; Aider’s URL scraping uses sync Playwright. `core/engine/aider_engine.py` runs `coder.run()` in a single-worker `ThreadPoolExecutor` so `detect_urls` stays enabled without asyncio conflicts. Reload MCP after code changes.

---

## Task specs (experimental)

Optional **bidirectional task specs** under the workspace (not in git unless you commit them):

```text
<workspace>/.mcp-coder/
  spec-template.md              # step task template (planner-owned sections)
  spec-epic-template.md         # epic template (multi-step features)
  spec-report-template.md       # MCP report template (auto-used; do not copy by hand)
  specs/epics/<slug>.md         # epic — planner; links step tasks
  specs/tasks/<epic>-<step>.md  # one step task per delegate (keep for audit)
  specs/reports/<same-name>.md  # MCP append-only Run log per step task
```

**Bootstrap on MCP start** (`main.py --mcp`):

| Path | Behavior |
|------|----------|
| Templates + `specs/{tasks,epics,reports}/` | Created if missing (never overwrites templates) |
| `.cursor/rules/use-mcp-coder.mdc` | **One** managed rule; content from **policy** (`default` \| `strict`); updated on MCP restart |

Consumer workspaces get **exactly one** mcp-coder rule — no duplicate or conflicting delegation files. **default** vs **strict** swaps content in place. Old managed files (`mcp-coder-delegate.mdc`, etc.) are removed on restart. Set `cursor_rules_policy` in config, **restart MCP**.

Consumer bundles live in **`resources/`** (`spec-template.md`, `cursor-rules/`, `examples/config.yaml`). Not loaded in this repo’s Cursor sessions. Dev rules: **`.cursor/rules/`**.

No manual copy for specs or Cursor rules. Disable with `MCP_CODER_SYNC_CURSOR_RULE=0` or `cursor_rules.sync: false` in workspace config. Hand-edited files without `mcp_coder_managed: true` are never overwritten.

**`config.yaml` is different** — user-owned settings; mcp-coder does not create or overwrite it (copy from `resources/examples/config.yaml` if you want session policy / `host_transcript` defaults).

**Cursor (planner)** owns epic + step task specs (Goal → Plan, Done when checkboxes). **mcp-coder** writes **reports** only (`specs/reports/` — Run log, Status `delegated_ok` \| `blocked`). Mark step task `status: done` in the task file after you verify tests. **Aider** edits repo files only.

Pass optional `spec_path` (step task under `tasks/`) to `delegate_to_agent`:

- `.mcp-coder/specs/tasks/my-epic-02-cli.md`
- `tasks/my-epic-02-cli.md` (shorthand)

**Review loop (same step spec, multiple calls):**

- `mode=review` — worker questions/suggestions only (`target_files=[]`); MCP appends **Worker feedback** on the report
- Planner updates task spec (`revision++`, `status: ready`)
- `mode=implement` (default) — edits `target_files` (include files to **read** for imports)

See [docs/notes/spec-review-loop.md](docs/notes/spec-review-loop.md).

If the file is missing, the tool returns `outcome: invalid_spec` (points at `spec-template.md`) and logs the attempt without calling Aider.

**Prompt order when spec is set:** host transcript (if `host_transcript: dump`) → compiled spec sections → `task` → `context_summary`.

Response adds `outcome`, `spec_path`, `spec_report_path`, `spec_sha256`, `spec_bytes`. See `docs/notes/storage-and-linking.md` and `resources/spec-template.md`.

---

## Cursor `mcp.json`

**Consumer repo:** copy [`resources/examples/mcp.json`](resources/examples/mcp.json) → `<project>/.cursor/mcp.json`, replace `/PATH/TO/mcp_coder`, restart Cursor. Full steps: [`resources/examples/MCP_SETUP.md`](resources/examples/MCP_SETUP.md).

Template uses `envFile` → mcp-coder `.env` so API keys stay in the mcp-coder checkout. `cwd` is `${workspaceFolder}` (the consumer repo Aider edits).

**Cannot auto-sync:** Cursor must read `mcp.json` before MCP starts — unlike `use-mcp-coder.mdc` and `spec-template.md`.

### Tool: `delegate_to_agent`

| Argument | Required | Notes |
|----------|----------|-------|
| `task` | yes | What to implement now |
| `target_files` | yes | Repo-relative paths for Aider `fnames` |
| `context_summary` | yes | Decisions/constraints from Cursor chat |
| `backend` | no | Default `aider` |

Returns JSON: `success`, `output`, `files_changed`, `session_reused`, `session_reason`, `session_policy`, `mcp_session_id`, `log_path`, `executor_reused`, `executor_recreated`.

Each call appends one line to the session log under home:

`~/.mcp-coder/projects/<project_key>/sessions/<mcp_session_id>/delegations.jsonl`

**Where is `<project_key>`?** Derived from the MCP process **`cwd`** (Cursor: opened folder). Optional mirror to `<workspace>/.mcp-coder/logs/delegations.jsonl` via `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE=1`.

Brief traces go to **stderr** (Cursor MCP log / terminal), not stdout:

```
[mcp-coder] ← delegate_to_agent id=c5952601… backend=aider files=[index.html] ws=…/mcp_coder_test_proj
[mcp-coder] → id=c5952601… success=true 6200ms changed=[index.html]
           log: ~/.mcp-coder/projects/<project_key>/sessions/<mcp_session_id>/delegations.jsonl
```

---

## Run manually

```bash
python main.py --mcp
# or
mcp-coder
```

---

## Execution adapters (swap backends)

Delegated runs go through a small **adapter layer** so the MCP server never imports Aider directly:

```
core/engine/
  base.py           # ExecutionEngine (ABC), ExecutionResult
  factory.py        # get_engine(backend), register_engine()
  git_diff.py       # shared files_changed via git
  aider_engine.py   # @register_engine("aider") — shipped in 1.0
  opencode_engine.py  # stub / notes for a future backend
```

- MCP tool `backend` selects the adapter (default `aider`; env `MCP_CODER_DEFAULT_BACKEND`).
- To add another CLI tool: subclass `ExecutionEngine`, implement `run()`, call `@register_engine("your_id")`, import the module from `core/engine/__init__.py`.

See [docs/PHASES.md](docs/PHASES.md) § Adapter architecture.

### Aider (default backend)

Uses Aider’s **unofficial** Python API. Delegations run headless with defaults equivalent to:

| CLI flag | Delegation default |
|----------|-------------------|
| `--yes-always` | `InputOutput(yes=True, pretty=False, fancy_input=False)` |
| `--no-auto-commits` | `auto_commits=False` |
| `--no-dirty-commits` | `dirty_commits=False` |
| (optional) `--no-git` | `MCP_CODER_AIDER_USE_GIT=0` |

Override via `MCP_CODER_AIDER_*` in `.env` (see `.env.example`). See [Aider scripting docs](https://aider.chat/docs/scripting.html).

---

## Delegation log viewer (human review)

Parse `delegations.jsonl` in a simple browser UI (newest first, filter, expand details, copy file paths).

**Option A — point at a workspace (merges all session logs from home):**

```bash
.venv/bin/python scripts/view_delegations.py --workspace /path/to/mcp_coder_test_proj

# or a single session log file
.venv/bin/python scripts/view_delegations.py ~/.mcp-coder/projects/<project_key>/sessions/<id>/delegations.jsonl

# shorthand
make view-logs ARGS="--workspace /path/to/mcp_coder_test_proj"
```

Opens http://127.0.0.1:8765/ and loads that file automatically.

**Option B — no server:** open `tools/delegation_viewer.html` in a browser and use **Choose file** to pick any `delegations.jsonl`.

CLI / AI inspection tools can be added later (same JSONL format).

## Tests

```bash
./scripts/bootstrap.sh --locked --dev
pytest
# or: make install-dev && make test
```

---

## Related projects

- [context_optimizer_proxy](https://github.com/amirharati/context_optimizer_proxy) — per-turn LLM optimization (separate from per-task delegation here). Optional future composition; not wired in 1.0.
