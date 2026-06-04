from core.engine.git_diff import files_changed_for_delegation, snapshot_mtimes


def test_files_changed_for_delegation_detects_mtime(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("v1\n", encoding="utf-8")
    before = snapshot_mtimes(str(tmp_path), ["a.py"])
    f.write_text("v2\n", encoding="utf-8")
    changed = files_changed_for_delegation(str(tmp_path), ["a.py"], before)
    assert changed == ["a.py"]
