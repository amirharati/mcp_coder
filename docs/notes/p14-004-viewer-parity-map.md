# P14-004 viewer parity map

> First-class deliverable from the P14-004 logging depth audit (4b).
> One row per emit-site event type. *Handler present* = a branch exists in
> `core/cli/delegation_view_enrich.py::_build_view_events()`.
> *Fields dropped* = top-level keys in the JSONL record that the handler does
> not surface in its `detail` dict. *Truncation* = viewer-side clipping
> (builders in `trace.py` already truncate at write time; this column only
> flags additional viewer truncation).

| event_type | emit site (file:fn) | handler present | fields surfaced | fields dropped | truncation |
|---|---|---|---|---|---|
| `trace_header` | `core/observability/trace.py:ensure_trace_header` | yes (skipped `continue`) | — | — | — |
| `compile_event` | `core/observability/trace.py:build_compile_event_record` | yes (598) | `stage`, `status`, `brief`, `body`, `byte_count`, `sha256`, `skip_reason`, llm fields (model, tokens, duration_ms, prompt/response preview+body, thinking_preview, thinking_tokens, policy_applied), `mechanical_brief` | `source_path`, `byte_start`, `byte_end`, `last_source_line` | — |
| `llm_call` | `core/observability/trace.py:build_trace_record` / `build_executor_llm_trace_record` | yes (703) | role, model, tokens (in/out/total/reasoning), thinking_tokens, thinking_body, thinking_preview, duration_ms, prompt/response body+preview, policy_applied; workspace_summarizer gets index_path+housekeeping | executor: `call_index` (P14-ISS-001); `cached_tokens` in tokens dict (not surfaced by handler) | — |
| `action` | `core/observability/trace.py:build_action_trace_record` | yes (773, emits step divider only) | — (emits divider, not action content) | `kind`, `detail`, `step_index` (all dropped — handler only emits a step divider) | — |
| `proxy_llm_call` | `core/observability/trace.py:build_proxy_llm_call_record` → `core/observability/local.py:487` | yes (790) | step_index, call_index, model, tokens_in, call_type, status_code, wire_latency_ms, attribution_source, prompt_format, system_prompt, system_chars, task, task_chars, context_turns, context_chars, context, total_messages, request_params, policy_applied, raw_request, prompt_preview | `ok`, `provider` | — |
| `backend_llm_call` | `core/observability/trace.py:build_backend_llm_call_record` → `core/observability/local.py:429` | yes (861) | step_index, call_index, model, tokens_out, tokens_in, thinking_tokens, duration_ms, status_code, wire_latency_ms, policy_applied, response_body, response_preview, thinking_body, thinking_preview, raw_response | `ok`, `call_type`, `provider` | — |
| `supervisor_loop_start` | `core/engine/supervisor_agent.py:1162` | yes (909) | event_type, loop_id, max_turns, turn_count, aborts_count | — | — |
| `supervisor_turn_start` | `core/engine/supervisor_agent.py:1171` | yes (934) | event_type, loop_id, turn_index | — | — |
| `supervisor_turn_end` | `core/engine/supervisor_agent.py:1187` | yes (950) | event_type, loop_id, turn_index, worker_outcome, checks_result, duration_ms | — | — |
| `supervisor_decision` | `core/engine/supervisor_agent.py:1199` | yes (979) | event_type, loop_id, turn_index, action, reason, model, tokens, duration_ms | — | — |
| `supervisor_outer_loop_start` | supervisor outer loop (legacy, P12-001 replaced) | yes (1009) | event_type, loop_id, cycle_index, reason | — | — |
| `supervisor_outer_loop_decision` | supervisor outer loop (legacy) | yes (1026) | event_type, loop_id, cycle_index, action, reason, reviewer_outcome | — | — |
| `supervisor_outer_loop_end` | supervisor outer loop (legacy) | yes (1052) | event_type, loop_id, cycle_index, action, reason, reviewer_outcome | — | — |
| `supervisor_turn_decision` | `core/engine/supervised_io.py:537` | yes (1078) | event_type, loop_id, turn_index, action, reason, risk_level, question_present, llm_used, duration_ms | — | — |
| `supervisor_loop_end` | `core/engine/supervisor_agent.py:1218` | yes (1108) | event_type, loop_id, end_reason, final_action, turns_completed, final_decision, turn_count, aborts_count | — | — |
| `supervisor_paused` | `core/engine/supervisor_agent.py:923` | yes (1145) | event_type, resume_token, turn_index, pause_reason, questions, expires_at, raw | — | — |
| `supervisor_resumed` | `core/engine/supervisor_agent.py:419` | yes (1173) | event_type, resume_token, resumed_at_turn, project_key, host_answer_chars, resume_reason, raw | — | — |
| `supervisor_state_abandoned` | `core/engine/supervisor_agent.py` | yes (1200) | event_type, resume_token, project_key, pause_reason, raw | — | — |
| `supervisor_session_reset` | `core/engine/supervisor_agent.py:524` | **YES (P14-004)** | turn_index, reason | — | — |
| `supervisor_intercept` | `core/engine/supervised_io.py:_emit_supervisor_intercept` (369) | **YES (P14-004)** | classification, decision, reasoning, question_preview, mentioned_paths, context_ref, llm_used, duration_ms, loop_id, turn_index | — | reasoning truncated to 200 chars in builder (not viewer) |
| `supervisor_tool_call` | `core/engine/supervisor_tool_runner.py:210` | **YES (P14-004)** | tool, delegation_id | — | — |
| `human_gate_opened` | `core/engine/supervised_io.py:_emit_gate_event` (306) | **YES (P14-004)** | risk_tier, question_preview | — | — |
| `human_gate_answered` | `core/engine/supervised_io.py:_emit_gate_event` (306) | **YES (P14-004)** | risk_tier, question_preview, answer_preview | — | — |
| `human_gate_timeout` | `core/engine/supervised_io.py:_emit_gate_event` (306) | **YES (P14-004)** | risk_tier, question_preview, timeout_s | — | — |
| `clarity_result` | `core/engine/supervisor_agent.py` (via `_emit`) | yes (1220) | status, ran, passed, has_questions, questions_count, questions, clarity_round_index, clarity_round_cap, clarity_auto_passed, error | — | — |
| `delegation_lifecycle_start` | `core/engine/supervisor_agent.py:1075` | yes (1267) | event_type, project_key, spec_path, session_policy, session_action, mcp_session_id, resumed, raw | — | — |
| `delegation_lifecycle_end` | `core/engine/supervisor_agent.py:1148` | yes (1291) | event_type, project_key, outcome, phase_summary, reviewer_pass_result, raw | — | — |
| `delegation_phase_start` | `core/engine/supervisor_agent.py:1100` | yes (1318) | event_type, project_key, phase, resumed, raw | — | — |
| `delegation_phase_end` | `core/engine/supervisor_agent.py:1120` | yes (1340) | event_type, project_key, phase, status, detail, raw | — | — |
| `agent_checkpoint_saved` | `core/engine/supervisor_agent.py:1015` | yes (1368) | event_type, project_key, last_delegation_id, last_outcome, file_path, delegation_id, raw | — | — |
| `agent_checkpoint_save_failed` | `core/engine/supervisor_agent.py:1027` | **YES (P14-004)** | error | — | — |
| `agent_rehydrated` | `core/engine/supervisor_agent.py:316` | yes (1396) | event_type, project_key, last_delegation_id, last_outcome, last_finished_at, delegation_id, raw | — | — |
| `project_state_loaded` | `core/engine/supervisor_agent.py:1322` | yes (1424) | event_type, project_key, raw | `decisions_count`, `open_risks_count`, `hot_areas_count`, `file_path` (all dropped) | — |
| `project_state_saved` | `core/engine/supervisor_agent.py:950` | yes (1442) | event_type, project_key, hot_areas_updated, decisions_added, risks_added, file_path, raw | — | — |
| `tool_call` | `core/observability/trace.py:build_tool_call_trace_record` | yes (1474) | step_index, tool, path, bytes_written, command, args, exit_code | — | command clipped to 80 chars in summary |

## Key

- **Handler present: YES (P14-004)** = handler added by this task (step 22 of P14-004-plan.md).
- Field names in the "emit site" column reference the function that constructs the record dict; `_emit()` in `supervisor_agent.py` is the generic dispatch.
- Truncation at write time: builders in `trace.py` apply `_truncate_preview` (500 chars) and `_truncate_brief` (200 chars) before writing to JSONL. This table only flags **viewer-side** truncation (where the viewer clips data already present on disk).