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

---

### Extension: Tracking Repo as Gatekeeper Enforcement Layer

The original Gatekeeper design is **pre-emptive** — restrict access, route writes through controlled tools, enforce templates on the way in. This works well when all agents are cooperative and use the provided tools. But it has a gap: an agent that calls a raw file-write tool directly can bypass the gate entirely, and there is no way to detect it after the fact.

The **workspace history / tracking repo** (delegation-scoped snapshots — see [WORKSPACE_HISTORY.md](./WORKSPACE_HISTORY.md)) closes this gap by making the Gatekeeper **retrospective** as well:

- **Pre-gate:** a snapshot is taken before each delegation. This establishes an exact baseline — every file, every byte.
- **Post-gate:** after delegation completes, the diff against the baseline reveals what *actually* changed. Any protected doc that was touched — even via a raw write that bypassed the gate — shows up in the diff.

This gives you two enforcement modes that complement each other:

| Mode | When | What it does |
|------|------|-------------|
| **Pre-emptive** | Before delegation | Restricts access; routes writes through Gatekeeper tools |
| **Retrospective** | After delegation | Diffs snapshot vs baseline; flags any protected file that changed outside the gate |

The retrospective mode does not require perfect pre-emptive enforcement. Even if a rogue write slips through, the tracking layer catches it, attributes it to a specific delegation ID, and can surface it in the response or block the outcome (reject the delegation result, mark it as a policy violation).

**Why this matters for docs-as-DB too:**  
If structured tracking docs (backlog, issue tracker) are managed as DB views, the Gatekeeper can enforce that the markdown view files are never written directly — the snapshot diff will immediately expose any direct edit as a policy violation, separate from the intended DB-tool write path. The two ideas reinforce each other: DB views make writes *structured*; the tracking repo makes violations *visible*.

---

### Extension: Structured Docs as DB Views

A natural evolution of the Gatekeeper is to treat **structured tracking documents** (backlogs, issue trackers, phase boards, ADRs) not as editable markdown files but as **compiled views over a database**. The DB is the source of truth; the markdown is rendered output.

**The problem this solves:**  
Agents today do fragile string-replacement on markdown tables to update status rows, add backlog items, or close issues. This breaks constantly — wrong match, wrong line, concurrent edits, trailing whitespace. The Gatekeeper approach above solves *who* can write; the DB-view approach solves *how* the write is structured.

**Core idea:**  
- The Gatekeeper (or main MCP) exposes structured tools: `add_tracked_item(type, id, fields)`, `update_tracked_item(...)`, `render_doc(type)`.
- Under the hood: SQLite stores the records.
- The markdown file is regenerated after each write — agents never touch it directly.
- Humans who want to edit go through the same tools (CLI or MCP) or edit a simple YAML/structured input format, never the raw markdown table.

**Why this pairs well with the Gatekeeper:**  
The Gatekeeper already controls *who can write* to protected docs. Adding DB-backed views means the Gatekeeper also controls *the write format* — no freeform text edits to structured tables, only well-typed record operations. This eliminates an entire class of agent errors.

**The human-edit tension:**  
The main objection is that humans sometimes want to edit docs directly in their editor. Two approaches:
- **Strict (DB only):** Markdown is read-only output; humans edit via CLI (`mcp-coder backlog add ...`). Simple, clean, but requires tooling discipline.
- **Frontmatter hybrid:** Structured fields live in YAML frontmatter per item; prose lives below. Parser reads frontmatter; regeneration preserves prose. More forgiving but harder to keep consistent.

The strict approach is cleaner for agent-heavy workflows. The hybrid is more practical when humans are the primary editors. The right choice depends on the doc type: pure tracking tables (backlog, issues) → strict; design notes with narrative → hybrid or leave as plain markdown.

**Potential issues and mitigations:**

| Issue | Mitigation |
|-------|-----------|
| Markdown and DB get out of sync if someone edits the .md directly | Policy: .md files are marked read-only in the Gatekeeper; writes rejected |
| View regeneration overwrites hand-written prose in the doc | Only regenerate structured sections (delimited blocks); prose sections are preserved |
| Schema changes break old DB rows | Migrations — same problem as any DB; keep schemas simple and additive |
| Humans resist CLI-only edits | Provide a thin web/TUI view or an MCP tool that Cursor can call conversationally |

**Scope note:**  
This is a product feature mcp-coder could provide to *any* workspace — not just for managing mcp-coder's own docs. A workspace opts in by initializing tracked doc types (`mcp-coder docs init backlog`). From that point, agents call structured MCP tools; markdown views are always fresh and consistent.