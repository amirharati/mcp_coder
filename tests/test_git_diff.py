import subprocess

from core.engine.git_diff import (
    compute_files_unexpected,
    files_changed_for_delegation,
    files_touched_since_snapshot,
    snapshot_git_dirty,
    snapshot_mtimes,
)


def _git_init_commit(repo: str, files: dict[str, str]) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    for name, content in files.items():
        path = f"{repo}/{name}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.run(["git", "add", name], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)


def test_files_changed_for_delegation_detects_mtime(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("v1\n", encoding="utf-8")
    before = snapshot_mtimes(str(tmp_path), ["a.py"])
    f.write_text("v2\n", encoding="utf-8")
    changed = files_changed_for_delegation(str(tmp_path), ["a.py"], before)
    assert changed == ["a.py"]


def test_snapshot_git_dirty_delta_tracked_and_untracked(tmp_path):
    _git_init_commit(str(tmp_path), {"a.py": "v1\n"})
    before = snapshot_git_dirty(str(tmp_path))
    assert before == set()

    (tmp_path / "a.py").write_text("v2\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("x\n", encoding="utf-8")

    after = snapshot_git_dirty(str(tmp_path))
    touched = sorted(after - before)
    assert touched == ["a.py", "new.py"]


def test_files_touched_since_snapshot_ignores_preexisting_dirty(tmp_path):
    _git_init_commit(str(tmp_path), {"a.py": "v1\n", "stale.py": "old\n"})
    (tmp_path / "stale.py").write_text("already dirty\n", encoding="utf-8")
    before = snapshot_git_dirty(str(tmp_path))
    assert "stale.py" in before

    (tmp_path / "a.py").write_text("v2\n", encoding="utf-8")
    changed, used_git = files_touched_since_snapshot(
        str(tmp_path), before, target_files=["a.py"]
    )
    assert used_git is True
    assert changed == ["a.py"]


def test_files_touched_since_snapshot_non_git_fallback_mtime(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("v1\n", encoding="utf-8")
    before_mtimes = snapshot_mtimes(str(tmp_path), ["a.py"])
    f.write_text("v2\n", encoding="utf-8")
    changed, used_git = files_touched_since_snapshot(
        str(tmp_path),
        None,
        target_files=["a.py"],
        before_mtimes=before_mtimes,
    )
    assert used_git is False
    assert changed == ["a.py"]


def test_compute_files_unexpected(tmp_path):
    unexpected = compute_files_unexpected(
        ["src/a.py", "src/extra.py"],
        ["src/a.py", "./src/b.py"],
        used_git=True,
    )
    assert unexpected == ["src/extra.py"]

    assert compute_files_unexpected(["a.py"], ["a.py"], used_git=False) == []

    assert compute_files_unexpected(
        ["a.py", "b.py"],
        ["a.py"],
        attribution_source="manifest",
    ) == ["b.py"]
