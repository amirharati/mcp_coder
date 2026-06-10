<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - May inform BL-* items; does not override docs/IDEA.md.
  - Do not treat as shipped product design without user + backlog entry.
  - Origin: discussion with Grok (2026-06-09) on LLM agentic loop logging for training.
  - Strategy: build as a separate product; use mcp-coder V1 as the first playground/client.
    Once the logging stack proves useful here, extract and open-source it for broader use.
-->

# Agentic Loop Logging — Full Interaction Capture for Training, Debugging & Research

**Status:** Idea — strategy: separate product, mcp-coder V1 as first playground (see §Relation to mcp-coder below)
**Origin:** Grok conversation, 2026-06-09
**Related:** [REASONING_TRACE_REUSE.md](./REASONING_TRACE_REUSE.md) · [WORKSPACE_HISTORY.md](./WORKSPACE_HISTORY.md)

---

## The core idea

Log the **full agentic loop interaction** — prompts, completions, tool calls/results, thinking/reasoning tokens, retries, reflections, outcomes, metadata — for every agent session. Store it compressed, curate it intelligently, and use it as fuel for:

- Failure mode discovery (systematic, not anecdotal)
- Simple predictor models (next-tool, success probability, context need)
- Context builder training (what context actually led to good outcomes)
- Fine-tuning small LLMs on real, in-distribution agentic trajectories
- Community open dataset for broader research

The key insight: **even partial or summarized reasoning is highly valuable** — and with smart filtering, a "huge amount of data" becomes manageable high-signal data rather than expensive noise.

---

## Why now / why useful

Full agentic traces with thinking tokens, tool outcomes, and failures are still scarce in 2026. Most public datasets are synthetic or benchmark-generated. Real in-the-wild agent loops contain:

- **Failure modes** that benchmarks miss — loops, tool misuse, context pollution
- **Reasoning traces** (the "why" behind decisions, not just the output)
- **Real retry/reflection patterns** — where models recover vs. collapse
- **Domain-specific signal** — far higher quality for fine-tuning than generic public data

Recent research shows that selectively mining *beneficial actions from failed trajectories* (not just successes) beats standard rejection-sampling fine-tuning on hard tasks. This makes failures first-class citizens in the dataset, not discards.

---

## Storage: what the numbers look like

All figures normalized per million tokens processed through a rich agent loop (~10k tokens/loop average — prompts + reasoning + tool calls + context).

| Storage type | Size per million tokens | Notes |
|---|---|---|
| Raw uncompressed JSON | 8–20 MB | Full verbose, every span duplicated |
| After gzip (JSONL.gz) | 1.5–4 MB | Simple, keeps everything |
| **Best: Parquet + zstd / ClickHouse** | **1.0–1.8 MB** | Recommended; columnar + compression |
| Fully processed (smart pipeline) | 150–500 KB | After trimming + summarization + novelty filter |

**Practical daily/monthly for one heavy power user (~10M tokens/day):**

| Tier | Per day | Per month |
|---|---|---|
| Raw at best compression | 10–18 MB | 300–540 MB |
| After full smart pipeline | 1.5–5 MB | 50–150 MB |

**Small group (3–5 power users, ~50M tokens/day):**

| Tier | Per day | Per month |
|---|---|---|
| Raw at best compression | 50–90 MB | 1.5–2.7 GB |
| After full smart pipeline | 8–25 MB | 250–750 MB |

**Conclusion:** For personal or small-group use, logging everything raw at best compression is trivial — roughly the size of a few photos per day for one heavy user. The smart pipeline is a multiplier, not a prerequisite for starting.

---

## Bootstrap sequence (important — don't skip this)

The three-stage filter below is the **steady-state** design, not the starting point. Building the classifier before you have data to train it is a common mistake. The correct order:

```
Week 1–2   Log everything raw — no filtering, no classifier
           Focus: get the capture infrastructure right (schema, compression, versioning)

Week 2–4   Manual exploration + clustering on the first batch
           Embed traces; run HDBSCAN; inspect cluster contents manually
           → Discover the 10–30 dominant common patterns empirically

Week 3–6   Train the first classifier on discovered patterns
           Labels come from clustering output + heuristics, not human annotation
           → Now you have a real filter; deploy Stage 1 + Stage 2

Month 2+   Add LLM judge (Stage 3) once classifier is stable
           → Full three-stage pipeline; begin curating training dataset

Month 3+   First model fine-tunes using curated traces + synthetic expansion
```

The key point: **raw logging is not a prototype state — it is the correct first state**. It also means you capture everything from day one and can retroactively apply better filters to historical data as the pipeline matures.

---

## The smart pipeline: entropy-based curation

Most interactions (90%+) are repetitive common patterns. The pipeline is designed to surface the rare, high-value fraction without expensive processing on everything.

### Three-stage filter

```
Incoming trace
   │
   ▼
[Stage 1] Cheap heuristics (100% of traces, ~ms)
   │  - Errors, retries, loops present?
   │  - Unusually high token count / steps?
   │  - Rare tool combinations?
   │  - Outcome mismatch (high effort, failure)?
   │  → Keep ~20–30% for further scoring
   │
   ▼
[Stage 2] Embedding-based novelty (runs on ~20-30%)
   │  - Embed: user intent summary + tool sequence + outcome + reasoning summary
   │  - Measure distance to historical distribution / cluster centroids
   │  - High distance → potentially interesting
   │  → Keep ~5–10% for LLM judging
   │
   ▼
[Stage 3] Small LLM judge (runs on ~5-10%)
   │  - Cheap fast model (7B–70B class, quantized)
   │  - Score on: unexpectedness, novel strategy, clear failure mode, new info
   │  - Output: 0–10 score + short justification
   │  → Keep top ~1–3% as "high value" → full or warm-tier storage
   │
   ▼
Tiered storage + export to training datasets
```

### Common-pattern classifier (additional layer)

Build a simple classifier to detect known repetitive patterns — complementing novelty filtering:

- **Discovery:** HDBSCAN / K-means on trace embeddings + frequent sequence mining on tool call sequences
- **Model:** Logistic regression or XGBoost on embeddings + metadata (trace length, token count, tool count, errors, latency)
- **Output:** P(trace belongs to known common pattern) + predicted pattern ID
- **Benefit:** The boring 90% gets aggregated (frequency, success rate, cost stats per pattern) rather than stored in full; the interesting tail gets escalated to the LLM judge

This classifier is itself one of the "simple model predictors" the system trains. It can also run at agent inference time ("this looks like a common pattern → use cached reasoning / fast path").

---

## Tiered storage model

| Tier | Retention | What to keep | Storage | Use case |
|---|---|---|---|---|
| Hot | Days–weeks | Full raw compressed traces | Parquet + zstd | Debugging, recent analysis |
| Warm | Months | Summarized traces + key excerpts | LLM summary + Parquet | Training datasets, failure mining |
| Cold | Years | Embeddings + aggregated stats | Vector index + columnar | Semantic search ("find similar failures") |

Trimming techniques for warm/cold:
- Strip redundant conversation history (keep deltas or last N turns + summary)
- PII redaction + tokenization of sensitive fields
- LLM-generated trace summaries (e.g. "Agent attempted 3 tool calls, succeeded on 2nd after reflection on stock mismatch")
- Keep only: outcome, error type, reasoning summary, tool sequence, novelty score for cold tier
- Common patterns → store once + reference count; aggregated metrics only

---

## Version tagging — a requirement, not optional

Every trace must be tagged with the exact configuration active at capture time. Without this, traces from before and after a pipeline change are incomparable and can *silently hurt* a fine-tune or classifier.

Required tags on every trace:
- **System version** — mcp-coder release / git SHA
- **Model versions** — builder LLM, executor model, validator model (all roles separately)
- **Pipeline flags** — which optional stages were active (`architect_pass`, `spec_validation`, `auto_verify`, `context_builder_llm`)
- **Config fingerprint** — hash of `config.yaml` relevant keys
- **Capture schema version** — so replay/migration is possible when fields change

This is cheap to implement (a few extra fields on every record) and catastrophically painful to reconstruct retroactively if missed.

---

## Training data yield

For one heavy personal power user (~30k raw traces/month, curating top 5–15%):

| Goal | Curated examples needed | Time to collect | Expected outcome |
|---|---|---|---|
| Simple classifier / predictor | 300–2,000 | 1–4 weeks | Good baseline |
| Context builder / summarizer | 500–3,000 | 2–6 weeks | Noticeable improvement in long sessions |
| Small LLM SFT (1–7B) on trajectories | 2,000–8,000+ | 1–2 months | Strong specialized agent behavior |
| + Synthetic expansion | Same seed + 10–50k synthetic | +1–2 weeks compute | Better generalization |

**Key insight:** For small-model fine-tuning, quality + diversity beats raw volume. 1k well-chosen real trajectories from your own agent can outperform 10k mediocre synthetic ones. 1–2 months of logging at power-user scale provides a sufficient seed.

Each trace generates multiple training examples:
- Full trajectory for SFT / behavior cloning
- Prefixes for next-action / tool prediction
- Reasoning summaries + outcomes for context builder or critic training
- Preference pairs (success vs. failure paths) if outcome scores or human feedback exist

### Synthetic expansion — the real multiplier

Once you have 1–2k curated real traces, the marginal cost of more data drops dramatically. A teacher model (frontier LLM) can generate variations of your real traces at 10–100× scale: paraphrase the task, change the codebase domain, introduce different failure modes, alter tool availability. The real traces provide grounding and realism; synthetic expansion provides diversity and scale.

The real seed — the in-distribution, real-usage traces only you can generate — is the hard part. The multiplication step is cheap. This makes the 1–2 month seed collection timeline very meaningful: it unlocks a much larger dataset with minimal additional effort.

---

## Possible community / open dataset angle

A longer-horizon idea: crowdsource real-world agentic traces into an open dataset — something that doesn't currently exist at scale. Proposed approach:

1. **Start personal** — Build the infra + pipeline for own use first (storage math is trivial)
2. **Open-source the pipeline early** — GitHub repo with schema, redaction, novelty judge prompts, Parquet exporter
3. **Demo value publicly** — Share anonymized insights from personal traces (top failure patterns, novel strategies found)
4. **Attract contributors** — Interested people join and handle harder parts (privacy governance, HF dataset hosting, community moderation, redaction rules)

Not a one-person job for the full vision, but the infra + personal-use pipeline is a one-person job and creates the foundation.

Key challenges if pursuing community version:
- **Privacy** — Mandatory automated redaction (Presidio + small LLM) before any upload; clear contributor ToS
- **Quality** — Classifier + novelty judge becomes the community curation engine
- **Standardization** — OpenTelemetry GenAI semantic conventions + Agent Data Protocol (ADP) for Hugging Face compatibility

---

## Relation to mcp-coder

### Product strategy

**Intended direction:** build as a **separate product**; use **mcp-coder V1 as the first playground and client**. As the logging stack proves useful on this project, extract it, clean the interface, open-source it — at which point it becomes usable by any agentic tool, not just mcp-coder. This project provides the first real-world stress-test; the logging tool provides value back here as a client.

> mcp-coder V1 → first playground → validate the stack → extract as open-source project → integrate here as client → broader community use

This avoids the "one person has to build everything" problem. The logging infra is scoped independently; mcp-coder only ever needs the client interface.

### mcp-coder already has a nascent substrate

The full pipeline is not a greenfield build — mcp-coder already emits most of the raw material:

| Existing artifact | What it captures | What's missing |
|---|---|---|
| `delegation_pipeline.jsonl` | All 10 pipeline phases, phase timings, builder brief, post-gateway diff, outcome | Reasoning/thinking tokens (not yet captured); token counts all null (BL-335) |
| `workspace_history.db` | Per-delegation outcomes, files changed, judgment checklist, RAG search index | No novelty score, no pattern ID |
| `delegation_rag.db` | Delegation summaries for FTS5 search | No embedding-based retrieval |
| LiteLLM (already in stack) | All model calls go through LiteLLM | Route A callback not yet wired; reasoning content stripped before storage |

**Practical implication:** "light integration" is not building a new logger — it is two targeted additions to what already exists:
1. Fix BL-335 (null token counts) to get cost/usage data per delegation
2. Wire REASONING_TRACE_REUSE.md Route A (LiteLLM callback) to capture reasoning tokens before Aider strips them

These two changes, plus adding version-tagging fields, give a usable raw trace dataset from existing infrastructure — no new systems needed for the bootstrap phase.

### Connection to Phase 4.5 open questions

Phase 4.5 Track 4 has several open empirical questions that currently require manual experiments:

| Phase 4.5 gap question | How logging answers it automatically |
|---|---|
| "Is the builder brief actually improving Aider output?" | Tag traces with `context_builder_llm: on/off`; compare outcome rates, retry counts, and edit quality across groups |
| "Does the picker miss relevant files in practice?" | Compare `candidate_files` vs `files_actually_changed` in post-gateway; miss rate is directly measurable |
| "Is delegation RAG used by planners?" | Log which RAG results were returned and whether the resulting delegation succeeded — adoption + value measurable |
| "Where does gpt-4o-mini fail vs other models?" | Group by executor model + outcome; retry count and `edit_format` error rate surface automatically |

These are currently unknowable without instrumentation. With the logging substrate in place, they become dashboardable from production data — no manual experiments needed.

### Relation to REASONING_TRACE_REUSE.md

That file covers capturing reasoning traces within the current session as live context (in-session injection, escalation signals). This file covers persistent logging of full interactions for offline training and research. They are complementary and share the same capture hook — REASONING_TRACE_REUSE.md Route A (LiteLLM callback). One implementation feeds both use cases: live context injection (that file) and durable training data (this file).

---

## Key references (from the Grok discussion)

- AgentTrace framework: operational + cognitive + contextual logging surfaces
- OpenTelemetry GenAI semantic conventions — community standard for agent/LLM/tool spans
- Agent Data Protocol (ADP) — 2026 unifying schema for trajectory → training data
- Hugging Face `agent-traces` dataset format — native viewer for timelines, prompts, tool calls, reasoning
- Langfuse (self-hosted, ClickHouse backend) — recommended starting platform for personal use
- Arize Phoenix — open-source, OpenTelemetry-native, good for evals
- Recent research: mining beneficial actions from failed trajectories beats rejection-sampling SFT on hard tasks
- AgentInstruct dataset: 1,866 high-quality trajectories produced strong agent fine-tune results — scale is not the bottleneck, quality is
