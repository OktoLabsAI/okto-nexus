"""Baseline inventory is repeatable and preserves a dirty laboratory clone."""
import hashlib
from pathlib import Path
import runpy
import subprocess


def test_baseline_preserves_renames_untracked_files_and_current_artifacts(tmp_path):
    capture = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                                "plans/r4_execution/audit_delivery.py"))["source_facts"]
    root = tmp_path / "laboratory with spaces"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)
    git("init", "-b", "feature/v0.2.0")
    (root / "pyproject.toml").write_text('[project]\nname="lab"\nversion="0.0.0"\n')
    (root / "old name.txt").write_text("original\n")
    git("add", "pyproject.toml", "old name.txt")
    git("-c", "user.name=Baseline Lab", "-c", "user.email=baseline@example.invalid",
        "commit", "-m", "Laboratory baseline")
    git("mv", "old name.txt", "renamed file.txt")
    (root / "renamed file.txt").write_text("original\nlocal modification\n")
    files = ["notes/untracked.txt",
             "vendor/ci/nexus_connector_core-0.2.52.dev0-py3-none-any.whl",
             "vendor/ci/okto_nexus_connector-0.5.0.dev0-py3-none-any.whl",
             "dist/okto_nexus-0.2.0.tar.gz"]
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"non-installable inventory fixture")
    def content_hashes():
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(root).parts}
    before = content_hashes()
    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    head = git("rev-parse", "HEAD")
    first = capture(root)
    assert first == capture(root)
    assert first["dirty_counts"] == {"RM": 1, "??": 4}
    assert first["core_wheels"] == {files[1]: before[files[1]]}
    assert first["distribution_artifacts"] == {name: before[name] for name in files[1:]}
    assert first["preexisting_file_hashes"][files[0]] == before[files[0]]
    assert content_hashes() == before
    assert git("rev-parse", "HEAD") == head
    assert git("status", "--porcelain=v1", "-z", "--untracked-files=all") == status
