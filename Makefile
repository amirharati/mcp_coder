.PHONY: venv install install-locked install-dev lock test mcp mcp-ps mcp-kill mcp-smoke logs-last server-logs-last test-ws

PYTHON ?= python3.12
# Workspace to test against (override: make mcp-smoke TEST_WS=/path/to/repo)
TEST_WS ?= $(CURDIR)/../mcp_coder_test_proj

venv:
	$(PYTHON) -m venv .venv

install:
	./scripts/bootstrap.sh

install-locked:
	./scripts/bootstrap.sh --locked

install-dev:
	./scripts/bootstrap.sh --locked --dev

lock:
	./scripts/lock-deps.sh

test:
	.venv/bin/pytest -q

# Manual stdio server (debug only — Cursor spawns its own; don't run both)
mcp:
	.venv/bin/python main.py --mcp

# List Cursor/manual mcp-coder processes
mcp-ps:
	@ps aux | grep "main.py --mcp" | grep -v grep || echo "(no mcp-coder processes)"

# Kill all main.py --mcp (then Reload Window in Cursor)
mcp-kill:
	-pkill -f "main.py --mcp" 2>/dev/null || true
	@echo "Done. In Cursor: Cmd+Shift+P → Developer: Reload Window"

# Verify on-disk code: policy, host, no old SESSION_POLICY constant
mcp-smoke:
	@echo "TEST_WS=$(TEST_WS)"
	@.venv/bin/python -c "import os, sys; \
ws=os.path.expanduser('$(TEST_WS)'); \
import core.logging.delegation_log as dl; \
from core.session.policy import resolve_session_policy; \
from core.host.cursor import CursorHostProvider; \
print('code ok:', not hasattr(dl, 'SESSION_POLICY')); \
print('session_policy:', resolve_session_policy(ws)); \
h=CursorHostProvider().resolve_active_session(ws); \
print('host:', h.host_kind, (h.host_session_id or '')[:8] or 'null'); \
cfg=os.path.join(ws, '.mcp-coder', 'config.yaml'); \
print('config.yaml:', 'yes' if os.path.isfile(cfg) else 'missing'); \
"

# Last delegation line for TEST_WS
logs-last:
	.venv/bin/python scripts/logs_last.py "$(TEST_WS)"

# Last server audit log lines (global; pass TEST_WS=/path on CLI for project file)
server-logs-last:
	.venv/bin/python scripts/server_logs_last.py $(if $(filter command line,$(origin TEST_WS)),"$(TEST_WS)",)

# Live delegate smoke (needs OPENROUTER_API_KEY in .env)
test-ws:
	cd "$(TEST_WS)" && ../mcp_coder/.venv/bin/python ../mcp_coder/scripts/smoke_delegation.py

view-logs:
	.venv/bin/python scripts/view_delegations.py --workspace "$(TEST_WS)" $(ARGS)
