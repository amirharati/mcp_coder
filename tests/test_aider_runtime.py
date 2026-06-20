from core.config.aider_runtime import (
    delegation_auto_commits,
    delegation_coder_kwargs,
    infer_run_success,
    supervised_execution_enabled,
)


def test_delegation_defaults_no_commits(monkeypatch):
    monkeypatch.delenv("MCP_CODER_AIDER_AUTO_COMMITS", raising=False)
    monkeypatch.delenv("AIDER_AUTO_COMMITS", raising=False)
    assert delegation_auto_commits() is False
    kwargs = delegation_coder_kwargs()
    assert kwargs["auto_commits"] is False
    assert kwargs["dirty_commits"] is False
    assert kwargs["suggest_shell_commands"] is False
    assert kwargs["stream"] is False


def test_infer_run_success_detects_litellm_error():
    class FakeIo:
        num_error_outputs = 0

    ok, err = infer_run_success(
        io=FakeIo(),
        output="litellm.NotFoundError: no model",
        partial_response="",
    )
    assert ok is False
    assert err


def test_infer_run_success_empty_output():
    class FakeIo:
        num_error_outputs = 0

    ok, err = infer_run_success(io=FakeIo(), output="", partial_response="")
    assert ok is False


def test_supervised_execution_enabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_CODER_SUPERVISED_EXEC", raising=False)
    assert supervised_execution_enabled(tmp_path) is True


def test_supervised_execution_disabled_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_CODER_SUPERVISED_EXEC", "0")
    assert supervised_execution_enabled(tmp_path) is False
