"""Tests for P7-003: compile_event provenance in per-delegation traces."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.observability import VERBOSITY_FULL, VERBOSITY_LEAN, VERBOSITY_STANDARD
from core.observability.trace import (
    STAGE_BUILDER_INPUT,
    STAGE_BUILDER_OUTPUT,
    STAGE_FINAL_EXECUTOR_PROMPT,
    STAGE_MECHANICAL_BRIEF,
    STAGE_VALIDATION_INPUT,
    TRACE_TYPE_COMPILE_EVENT,
    build_compile_event_record,
)
from server.mcp_server import _emit_compile_event, _emit_compile_provenance_pair


def test_build_compile_event_record_lean_hash_only():
    body = "mechanical brief content with sk-abcdefghijklmnopqrstuvwxyz123456"
    rec = build_compile_event_record(
        delegation_id="d-lean",
        stage=STAGE_MECHANICAL_BRIEF,
        verbosity=VERBOSITY_LEAN,
        text_body=body,
    )
    assert rec["type"] == TRACE_TYPE_COMPILE_EVENT
    assert rec["stage"] == STAGE_MECHANICAL_BRIEF
    assert "sha256" in rec
    assert "byte_count" in rec
    assert "brief" not in rec
    assert rec["body"] == "mechanical brief content with sk-***"


def test_build_compile_event_record_standard_includes_brief():
    body = "x" * 500
    rec = build_compile_event_record(
        delegation_id="d-std",
        stage=STAGE_BUILDER_INPUT,
        verbosity=VERBOSITY_STANDARD,
        text_body=body,
    )
    assert "brief" in rec
    assert len(rec["brief"]) <= 200
    assert "body" in rec
    assert len(rec["body"]) == 500


def test_build_compile_event_record_full_includes_body():
    body = "full body text for compile stage"
    rec = build_compile_event_record(
        delegation_id="d-full",
        stage=STAGE_BUILDER_OUTPUT,
        verbosity=VERBOSITY_FULL,
        text_body=body,
    )
    assert rec["brief"] in rec["body"]
    assert rec["body"] == body


def test_build_compile_event_record_redacts_secrets():
    body = "api key sk-abcdefghijklmnopqrstuvwxyz123456 in prompt"
    rec = build_compile_event_record(
        delegation_id="d-redact",
        stage=STAGE_BUILDER_INPUT,
        verbosity=VERBOSITY_STANDARD,
        text_body=body,
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in rec["brief"]


def test_build_compile_event_record_validation_metadata():
    rec = build_compile_event_record(
        delegation_id="d-val",
        stage="validation_input",
        verbosity=VERBOSITY_LEAN,
        text_body="validate this",
        source_path="/tmp/chat.jsonl",
        last_source_line=42,
        byte_start=0,
        byte_end=128,
    )
    assert rec["source_path"] == "/tmp/chat.jsonl"
    assert rec["last_source_line"] == 42
    assert rec["byte_start"] == 0
    assert rec["byte_end"] == 128


def test_emit_compile_event_writes_to_trace(tmp_path):
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    _emit_compile_event(
        delegation_id="d-emit",
        stage=STAGE_MECHANICAL_BRIEF,
        text_body="brief text",
        workspace=str(tmp_path),
        session_dir=session_dir,
        obs_verbosity=VERBOSITY_STANDARD,
    )
    trace_path = session_dir / "traces" / "d-emit.jsonl"
    assert trace_path.is_file()
    records = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
    compile_events = [r for r in records if r.get("type") == TRACE_TYPE_COMPILE_EVENT]
    assert len(compile_events) == 1
    assert compile_events[0]["stage"] == STAGE_MECHANICAL_BRIEF


def test_emit_compile_provenance_pair_input_output(tmp_path):
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    _emit_compile_provenance_pair(
        delegation_id="d-pair",
        workspace=str(tmp_path),
        session_dir=session_dir,
        obs_verbosity=VERBOSITY_LEAN,
        input_stage=STAGE_BUILDER_INPUT,
        output_stage=STAGE_BUILDER_OUTPUT,
        provenance={"input_prompt": "in", "output_text": "out"},
    )
    trace_path = session_dir / "traces" / "d-pair.jsonl"
    records = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
    stages = [r["stage"] for r in records if r.get("type") == TRACE_TYPE_COMPILE_EVENT]
    assert stages == [STAGE_BUILDER_INPUT, STAGE_BUILDER_OUTPUT]


def test_emit_compile_provenance_pair_passes_byte_range_on_input(tmp_path):
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    _emit_compile_provenance_pair(
        delegation_id="d-bytes",
        workspace=str(tmp_path),
        session_dir=session_dir,
        obs_verbosity=VERBOSITY_LEAN,
        input_stage="validation_input",
        output_stage="validation_output",
        provenance={"input_prompt": "validate", "output_text": "ok"},
        source_path="/tmp/chat.jsonl",
        byte_start=0,
        byte_end=42,
        last_source_line=2,
    )
    trace_path = session_dir / "traces" / "d-bytes.jsonl"
    records = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
    validation_input = next(
        r for r in records if r.get("type") == TRACE_TYPE_COMPILE_EVENT and r["stage"] == "validation_input"
    )
    validation_output = next(
        r for r in records if r.get("type") == TRACE_TYPE_COMPILE_EVENT and r["stage"] == "validation_output"
    )
    assert validation_input["byte_start"] == 0
    assert validation_input["byte_end"] == 42
    assert validation_input["last_source_line"] == 2
    assert "byte_start" not in validation_output
    assert "byte_end" not in validation_output


def test_helper_pipeline_returns_provenance():
    from core.context.helper_llm_pipeline import apply_architect_pass, apply_builder_llm

    pkg = MagicMock()
    pkg.brief = "mechanical"
    spec_read = MagicMock()
    picker = MagicMock()

    arch_result = MagicMock()
    arch_result.success = True
    arch_result.plan = "## Architect plan\nDo X"
    arch_result.model = "m"
    arch_result.tokens = {"input": 1, "output": 2, "total": 3, "source": "x"}
    arch_result.duration_ms = 10
    arch_result.raw_output = "## Architect plan\nDo X"
    arch_result.error = None

    with patch(
        "core.engine.architect_pass_llm.run_architect_pass_llm",
        return_value=arch_result,
    ), patch(
        "core.context.architect_prompt.build_architect_pass_prompt",
        return_value="arch prompt",
    ):
        plan, err, record, prov = apply_architect_pass(
            context_package=pkg,
            spec_read=spec_read,
            picker_result=picker,
            workspace="/tmp",
            task="t",
            context_summary="ctx",
            host_transcript=None,
        )
    assert plan is not None
    assert prov["input_prompt"] == "arch prompt"
    assert prov["output_text"] == "## Architect plan\nDo X"

    builder_result = MagicMock()
    builder_result.success = False
    builder_result.brief = ""
    builder_result.model = "m"
    builder_result.tokens = {"source": "x"}
    builder_result.duration_ms = 5
    builder_result.raw_output = "raw fail"
    builder_result.error = "builder failed"

    with patch(
        "core.context.builder_history.gather_builder_history",
        return_value=MagicMock(same_spec=[], project_recent=[], prior_reasoning=[]),
    ), patch(
        "core.context.builder_prompt.build_builder_llm_prompt",
        return_value="builder prompt",
    ), patch(
        "core.engine.context_builder_llm.run_context_builder_llm",
        return_value=builder_result,
    ), patch(
        "core.observability.get_observability",
        return_value=MagicMock(capture_reasoning_enabled=lambda _w: False),
    ):
        _pkg, applied, error, _record, prov = apply_builder_llm(
            context_package=pkg,
            picker_result=picker,
            workspace="/tmp",
            task="t",
            context_summary="ctx",
            spec_rel_path=None,
            host_transcript=None,
        )
    assert not applied
    assert error == "builder failed"
    assert prov["input_prompt"] == "builder prompt"
    assert prov["output_text"] == "builder failed"


def test_delegate_emits_compile_events_without_bloating_jsonl(tmp_path, monkeypatch):
    """Integration: compile events in trace; delegations.jsonl stays lean."""
    from core.engine.base import ExecutionResult
    from server.mcp_server import delegate_to_agent

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "observability_verbosity: standard\n", encoding="utf-8"
    )
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "step.md"
    spec_path.write_text(
        "---\nfiles_edit:\n  - foo.py\n---\n\n# Step\n\n## Files\n\nfoo.py\n",
        encoding="utf-8",
    )
    (ws / "foo.py").write_text("# foo\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", "standard")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="ok",
        files_changed=["foo.py"],
        model="m",
        prompt_used="final executor prompt text",
    )
    engine = MagicMock()
    engine.model_name = "m"
    engine.capabilities.return_value = MagicMock()
    engine.run_context.return_value = fake

    builder_prov = {
        "input_prompt": "builder in",
        "output_text": "builder out",
    }
    arch_prov = {
        "input_prompt": "arch in",
        "output_text": "arch out",
    }

    def _fake_builder(**kwargs):
        pkg = kwargs["context_package"]
        return pkg, True, None, {"role": "context_builder"}, builder_prov

    def _fake_arch(**kwargs):
        return "## Architect plan\nx", None, {"role": "architect_pass"}, arch_prov

    with patch("server.mcp_server.get_engine", return_value=engine), patch(
        "server.mcp_server._shared_apply_builder_llm", side_effect=_fake_builder
    ), patch(
        "server.mcp_server._shared_apply_architect_pass", side_effect=_fake_arch
    ), patch(
        "server.mcp_server.spec_validation_enabled", return_value=False
    ), patch(
        "server.mcp_server.architect_pass_enabled", return_value=True
    ), patch(
        "server.mcp_server.context_builder_enabled", return_value=True
    ), patch(
        "server.mcp_server.context_builder_llm_enabled", return_value=True
    ), patch(
        "server.mcp_server.pick_candidate_files",
        return_value=MagicMock(suggested_edit_paths=["foo.py"]),
    ):
        raw = delegate_to_agent(
            task="t",
            target_files=["foo.py"],
            context_summary="ctx",
            spec_path="tasks/step.md",
            mode="implement",
        )

    resp = json.loads(raw)
    log_path = Path(resp["log_path"])
    deleg_record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert "compile_event" not in json.dumps(deleg_record)
    assert "body" not in json.dumps(deleg_record.get("context_block") or {})

    session_dir = log_path.parent
    trace_files = list((session_dir / "traces").glob("*.jsonl"))
    assert trace_files
    records = [
        json.loads(l)
        for l in trace_files[-1].read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    compile_stages = [
        r["stage"] for r in records if r.get("type") == TRACE_TYPE_COMPILE_EVENT
    ]
    assert STAGE_MECHANICAL_BRIEF in compile_stages
    assert STAGE_BUILDER_INPUT in compile_stages
    assert STAGE_BUILDER_OUTPUT in compile_stages
    assert STAGE_FINAL_EXECUTOR_PROMPT in compile_stages
    llm_calls = [r for r in records if r.get("type") == "llm_call"]
    assert llm_calls  # executor llm_call from P7-002 loop still present


def test_delegate_validation_input_includes_transcript_byte_range(tmp_path, monkeypatch):
    """Integration: validation_input compile_event carries host JSONL byte provenance."""
    from core.engine.base import ExecutionResult
    from core.engine.spec_validation_llm import SpecValidationLlmResult
    from core.host.base import HostSessionHint
    from core.host.cursor_transcript import load_cursor_transcript
    from server.mcp_server import delegate_to_agent

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".mcp-coder").mkdir()
    (ws / ".mcp-coder" / "config.yaml").write_text(
        "observability_verbosity: lean\nhost_transcript: dump\nspec_validation: true\n",
        encoding="utf-8",
    )
    spec_dir = ws / ".mcp-coder" / "specs" / "tasks"
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "step.md"
    spec_path.write_text(
        "---\nfiles_edit:\n  - foo.py\n---\n\n# Step\n\n## Files\n\nfoo.py\n",
        encoding="utf-8",
    )
    (ws / "foo.py").write_text("# foo\n", encoding="utf-8")

    transcript = tmp_path / "chat.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "user",
                "message": {"content": [{"type": "text", "text": "Use JSON files"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    expected = load_cursor_transcript(transcript)

    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="ok",
        files_changed=["foo.py"],
        model="m",
        prompt_used="final prompt",
    )
    engine = MagicMock()
    engine.model_name = "m"
    engine.capabilities.return_value = MagicMock()
    engine.run_context.return_value = fake

    ok = SpecValidationLlmResult(
        success=True,
        passed=True,
        clarifications=[],
        model="cheap-model",
        duration_ms=5,
    )
    hint = HostSessionHint(
        host_kind="cursor",
        host_session_id="sess-1",
        host_transcript_path=str(transcript.resolve()),
    )

    with patch("server.mcp_server.get_host_provider") as host_provider, patch(
        "server.mcp_server.get_engine", return_value=engine
    ), patch(
        "core.engine.spec_validation_llm.run_spec_validation_llm",
        return_value=ok,
    ), patch(
        "server.mcp_server.context_builder_enabled", return_value=False
    ), patch(
        "server.mcp_server.architect_pass_enabled", return_value=False
    ):
        host_provider.return_value.resolve_active_session.return_value = hint
        raw = delegate_to_agent(
            task="t",
            target_files=["foo.py"],
            context_summary="ctx",
            spec_path="tasks/step.md",
            mode="implement",
        )

    resp = json.loads(raw)
    log_path = Path(resp["log_path"])
    trace_files = list((log_path.parent / "traces").glob("*.jsonl"))
    records = [
        json.loads(line)
        for line in trace_files[-1].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validation_input = next(
        r
        for r in records
        if r.get("type") == TRACE_TYPE_COMPILE_EVENT and r.get("stage") == STAGE_VALIDATION_INPUT
    )
    assert validation_input["source_path"] == str(transcript.resolve())
    assert validation_input["byte_start"] == expected.source_byte_start
    assert validation_input["byte_end"] == expected.source_byte_end
    assert 0 <= validation_input["byte_start"] < validation_input["byte_end"] <= transcript.stat().st_size
    sliced = transcript.read_bytes()[validation_input["byte_start"] : validation_input["byte_end"]]
    sliced.decode("utf-8")
