<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - May inform BL-* / P1-199; does not override docs/IDEA.md.
  - Do not treat as shipped product design without user + backlog entry.
-->

**✅ Gatekeeper Idea — Summary** (related idea — see [IDEA.md](../IDEA.md) spec tools · [VISION_DOCS.md](../VISION_DOCS.md))

### Gatekeeper Concept Overview

The **Gatekeeper** is a dedicated layer responsible for protecting core documents (`specs/`, planning files, architecture decisions, brainstorming notes, etc.) from casual or uncontrolled modifications by AI agents.

**Core Philosophy**:  
"Core Documents are Sacred" — Once finalized, they should be mostly **immutable**. Changes must be controlled, versioned, and auditable.

---

### Why We Need a Gatekeeper

- Prevent AI agents from casually editing high-value documents during implementation.
- Enforce strict versioning and metadata.
- Keep a clean audit trail (who/when/which model changed what).
- Allow high-end models to do creative work early, then lock it down for cheap models during implementation.
- Reduce risk of drift and inconsistency.

---

### Proposed Architecture (Multi-MCP)

**1. Protected Zone**
- Folder: `specs/` (or `core-docs/`)
- Made **physically unreachable** to most agents using MCP Roots / filesystem restrictions.

**2. Gatekeeper MCP** (Dedicated Server)
- Low-intelligence / rule-heavy component (can even be mostly non-LLM).
- Has **exclusive write access** to the `specs/` folder.
- Acts as the only entity allowed to create, version, or modify protected files.

**3. Main MCP Wrapper** (Your current orchestrator)
- Smart layer (task optimization, memory, phase routing).
- Can **read** protected documents but **cannot** write to them directly.
- Must call the Gatekeeper when changes are needed.

**4. Other Agents** (Aider, sub-agents, etc.)
- Only have access through virtual tools.
- Cannot see or touch the `specs/` folder directly.

---

### Key Tools (Virtual Interface)

All agents interact with protected documents **only** through these tools:

- `read_protected_doc(task_id, filename)`
- `read_protected_doc_version(task_id, filename, version)`
- `propose_doc_amendment(task_id, filename, changes, reason)`
- `append_to_protected_log(task_id, log_type, content)`
- `list_protected_docs()`
- `get_doc_history(task_id)`
- `create_new_doc_version` (internal, called by Gatekeeper only)

---

### Core Rules / Behavior

- Core documents become **immutable** once marked `finalized`.
- Changes require formal `propose_amendment` → review → `approve_version`.
- Every file has rich metadata (created_by, timestamp, session_id, status, protection_level).
- Meeting notes and decisions are **append-only**.
- Gatekeeper enforces templates and validation on every write.

---

### Pros of Separate Gatekeeper MCP

- Stronger isolation and security.
- Easier to make it very strict and rule-based.
- Can be kept simple and cheap.
- Better auditability.

### Cons of Separate Gatekeeper

- Extra complexity (another server to run).
- More communication overhead (MCP tool calls between Main Wrapper and Gatekeeper).

---

**Decision Point for Later:**
- Start with **one MCP** (Main Wrapper acts as gatekeeper too) for simplicity.
- Later split into **dedicated Gatekeeper MCP** when the rules become complex or you want stronger isolation.

---

This document keeps the Gatekeeper idea **out of scope** for your current MCP Wrapper work, while giving you a clear blueprint for when you're ready to implement stronger document control.

Would you like me to refine this summary further before you save it?