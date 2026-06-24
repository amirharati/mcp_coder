"""T17-T18: DelegationSupervisor stores new fields; target_files dict split logic."""

from __future__ import annotations

from core.engine.supervisor import DelegationSupervisor


def test_supervisor_stores_project_state_summary_and_target_files(tmp_path):
    """T17: DelegationSupervisor stores project_state_summary and target_files from constructor."""
    supervisor = DelegationSupervisor(
        workspace_path=tmp_path,
        delegation_id="t17-deleg",
        spec_contract="files: foo.py",
        architect_plan=None,
        output_tail_provider=lambda: "",
        project_state_summary="### Recent decisions\n- Decision A (abc12345)",
        target_files={"files_edit": ["a.py", "b.py"], "files_read": ["c.md"]},
    )
    assert supervisor._project_state_summary == "### Recent decisions\n- Decision A (abc12345)"
    assert supervisor._target_files == {"files_edit": ["a.py", "b.py"], "files_read": ["c.md"]}


def test_supervisor_defaults_to_none_for_new_fields(tmp_path):
    """Verify backward-compat: omitting the new params defaults to None."""
    supervisor = DelegationSupervisor(
        workspace_path=tmp_path,
        delegation_id="t-defaults",
        spec_contract="files: foo.py",
        architect_plan=None,
        output_tail_provider=lambda: "",
    )
    assert supervisor._project_state_summary is None
    assert supervisor._target_files is None


def test_io_factory_target_files_dict_split_logic():
    """T18: Verify the target_files dict split logic (edit vs read)."""
    # This tests the same logic used in _io_factory's dict construction.
    edit_paths_rel = ["a.py", "b.py"]
    contract = ["a.py", "b.py", "c.md"]

    files_edit_norm = sorted({
        p.replace("\\", "/").lstrip("./") for p in edit_paths_rel if p
    })
    files_edit_set = set(files_edit_norm)
    files_read_norm = sorted({
        p.replace("\\", "/").lstrip("./")
        for p in (contract or [])
        if p and p.replace("\\", "/").lstrip("./") not in files_edit_set
    })
    target_files_dict = {
        "files_edit": files_edit_norm,
        "files_read": files_read_norm,
    }
    assert target_files_dict["files_edit"] == ["a.py", "b.py"]
    assert target_files_dict["files_read"] == ["c.md"]