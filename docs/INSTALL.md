# Install & reproducible environment

This doc lists **system prerequisites**, **Python version constraints**, and **two install paths**: flexible (from `pyproject.toml`) and **locked** (from `requirements-lock.txt`).

---

## Prerequisites

| Requirement | Why |
|---------------|-----|
| **Python 3.10, 3.11, or 3.12** | `aider-chat` does not publish wheels for 3.13+ |
| **git** | Aider uses git for diffs / `files_changed` |
| **OpenRouter API key** (for real delegations) | `OPENROUTER_API_KEY` — [get one](https://openrouter.ai/keys) |

Optional:

| Tool | Purpose |
|------|---------|
| `python3.12` on PATH | Recommended; matches `.python-version` and lock file |
| Cursor | MCP host for `delegate_to_agent` |

---

## What gets installed

### Runtime (required)

Declared in `pyproject.toml` and `requirements.in`:

| Package | Role |
|---------|------|
| **mcp** | MCP server (stdio), `delegate_to_agent` tool |
| **aider-chat** | Aider Python API (`Coder`, `Model`, `InputOutput`) |

Installing `aider-chat` pulls many transitive deps (LiteLLM, GitPython, httpx, …). Those are **pinned** in `requirements-lock.txt`.

### This repo

| Artifact | Role |
|----------|------|
| **mcp-coder** (editable) | `main.py`, `server/`, `core/` — install with `pip install -e .` |

Only the **aider** execution adapter is registered in Phase 1.0. Other backends (e.g. OpenCode) plug in via `core/engine/` — see README § Execution adapters.

### Development (optional)

| Package | Role |
|---------|------|
| **pytest** | Unit tests in `tests/` |

---

## Quick start (recommended: locked)

From the repo root:

```bash
chmod +x scripts/bootstrap.sh scripts/lock-deps.sh
./scripts/bootstrap.sh --locked --dev
```

Or with Make:

```bash
make install-dev
make test
```

Activates implicitly via `.venv/bin/...`:

```bash
source .venv/bin/activate
mcp-coder          # same as: python main.py --mcp
pytest
```

---

## Install paths

### A) Locked (reproducible)

Uses committed `requirements-lock.txt` (full `pip freeze` of a known-good env).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements-lock.txt
pip install -e . --no-deps
# optional dev:
pip install -r requirements-dev.txt
pip install -e . --no-deps
```

**When to use:** CI, new machine, “same versions as last time”.

### B) Flexible (from pyproject)

Resolves latest compatible versions within ranges in `pyproject.toml`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -e .              # runtime only
pip install -e ".[dev]"       # + pytest
```

**When to use:** day-to-day dev after bumping dependency ranges.

---

## Regenerating the lock file

After changing `pyproject.toml` / `requirements.in` or upgrading deps intentionally:

```bash
./scripts/lock-deps.sh
# or: make lock
```

Commit the updated `requirements-lock.txt`.

Verified combo when lock was generated (example — check file header):

- Python 3.12.x  
- `mcp` 1.27.x  
- `aider-chat` 0.86.x  

---

## File reference

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependency **ranges**, `mcp-coder` console script |
| `requirements.in` | Direct runtime deps (documentation mirror of pyproject) |
| `requirements-dev.in` | Direct dev deps |
| `requirements-lock.txt` | **Pinned** full runtime tree |
| `requirements-dev.txt` | Lock + pinned `pytest` |
| `scripts/bootstrap.sh` | One-command venv + install |
| `scripts/lock-deps.sh` | Regenerate `requirements-lock.txt` |
| `.python-version` | Hint for pyenv / mise (3.12) |

---

## Cursor MCP

After install, point Cursor at the venv Python (see [README.md](../README.md) § Cursor `mcp.json`). Set `cwd` to the **target repo** you want Aider to edit, not necessarily the `mcp_coder` repo.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No matching distribution found for aider-chat` | Use Python **≤ 3.12**, not 3.13 |
| `ModuleNotFoundError: aider` | `pip install aider-chat` or re-run bootstrap |
| MCP tool missing in Cursor | Restart Cursor; check `mcp.json` path to `.venv/bin/python` |
| Delegation fails immediately | Set `OPENROUTER_API_KEY` in `.env` or MCP `env`; check `AIDER_MODEL` uses `openrouter/` prefix |

---

## API keys & `.env`

| Task | Need `.env`? |
|------|----------------|
| `make install-dev`, `pytest` | No |
| MCP registers in Cursor | No |
| Real `delegate_to_agent` (LLM edits) | Yes — provider API key |

Copy [`.env.example`](../.env.example) → `.env` in your **workspace** (the repo Cursor sets as MCP `cwd`), or put keys in `mcp.json` → `env`.

The server loads `.env` automatically on start (`MCP_CODER_ENV_FILE` overrides path). `.env` is gitignored.

See [README.md](../README.md) for all `MCP_CODER_*` and `AIDER_MODEL` variables.
