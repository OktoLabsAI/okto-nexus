"""Prepare canonical artifact-path coverage; no app or worker execution."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, text):
    path = HERE / name
    assert not path.exists(), path
    path.write_text(text, encoding="utf-8", newline="\n")


old = (HERE / "worker_v2.py").read_text(encoding="utf-8")
needle = '@contextmanager\ndef observe(factory, artifacts):'
helper = '''def canonical_artifact_paths(factory, home):
    """Metadata only: mirror LocalArtifactStore root, never read file content."""
    storage_root = (home / "artifacts").resolve()
    assert storage_root.is_relative_to(home.resolve())
    expected = {f"j04-synthetic-artifact-{index:03}" for index in range(25)}
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("SELECT artifact_id,storage_path FROM artifacts "
            "WHERE artifact_id LIKE 'j04-synthetic-artifact-%' ORDER BY artifact_id").fetchall()
    assert {row["artifact_id"] for row in rows} == expected and len(rows) == 25
    mapping = []
    for row in rows:
        stored = row["storage_path"]
        assert isinstance(stored, str) and stored and not Path(stored).is_absolute()
        path = (storage_root / stored).resolve()
        assert path.is_relative_to(storage_root) and path != storage_root
        assert path.is_relative_to(home.parent.resolve()) and path.is_file()
        mapping.append({"artifact_id": row["artifact_id"], "storage_path": stored, "canonical_path": str(path)})
    return mapping


@contextmanager
def observe(factory, artifacts, canonical_paths):'''
assert old.count(needle) == 1
new = old.replace(needle, helper)
needle = '    report = {"rows_materialized": 0, "max_string_bytes": 0, "full_payload_materialized": [], "artifact_content_sql_reads": 0, "artifact_file_reads": []}'
replacement = needle + '\n    protected_paths = frozenset(Path(item["canonical_path"]).resolve() for item in canonical_paths)\n    assert protected_paths and len(canonical_paths) == 25\n    report["guarded_artifact_ids"] = 25\n    report["guarded_canonical_payload_paths"] = len(protected_paths)'
assert new.count(needle) == 1
new = new.replace(needle, replacement)
needle = '            if path.is_relative_to(artifacts):'
assert new.count(needle) == 1
new = new.replace(needle, '            if path.is_relative_to(artifacts) or path in protected_paths:')
needle = '    app = build_app(deps)\n    before = benchmark.productive(deps.connection_factory)'
assert new.count(needle) == 1
new = new.replace(needle, '    app = build_app(deps)\n    canonical_paths = canonical_artifact_paths(deps.connection_factory, home)\n    before = benchmark.productive(deps.connection_factory)')
needle = 'with observe(deps.connection_factory, home.parent / "synthetic-artifacts") as instrumentation:'
assert new.count(needle) == 1
new = new.replace(needle, 'with observe(deps.connection_factory, home.parent / "synthetic-artifacts", canonical_paths) as instrumentation:')
needle = 'return {"reads": reads, "instrumentation": instrumentation, "productive_rows_unchanged": True}'
assert new.count(needle) == 1
new = new.replace(needle, 'return {"reads": reads, "instrumentation": instrumentation, "productive_rows_unchanged": True,\n            "canonical_artifact_paths": canonical_paths}')
needle = '"instrumentation": instrumentation, "latencies_collected": False})'
assert new.count(needle) == 1
new = new.replace(needle, '"instrumentation": instrumentation, "canonical_artifact_paths": canonical_paths, "latencies_collected": False})')
ast.parse(new)
write("worker_v3.py", new)
old_runner = (HERE / "run_v2.py").read_text(encoding="utf-8")
runner = old_runner.replace('HERE / "PREPARED-v2.json"', 'HERE / "PREPARED-v3.json"').replace('HERE / "worker_v2.py"', 'HERE / "worker_v3.py"')
ast.parse(runner)
write("run_v3.py", runner)
diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="worker_v2.py", tofile="worker_v3.py"))
diff += "".join(difflib.unified_diff(old_runner.splitlines(True), runner.splitlines(True), fromfile="run_v2.py", tofile="run_v3.py"))
write("v3-counterparts.diff", diff)
manifest = json.loads((HERE / "PREPARED-v2.json").read_text(encoding="utf-8"))
for name in ("worker_v3.py", "run_v3.py", "prepare_v3.py", "v3-counterparts.diff"):
    manifest["helper_sha256"][str(HERE / name)] = sha(HERE / name)
manifest["antecedent_attempt2"] = {"qualification": "attempt2/qualification.json", "sha256": sha(HERE / "attempt2/qualification.json"),
    "status": "PASS_SCOPED_EXECUTED_ASSERTIONS", "limit": "Original file hook did not cover canonical storage paths after bootstrap"}
manifest["variant_delta"] = ["After bootstrap, capture only artifact_id/storage_path metadata for exactly25 expected IDs",
    "Resolve using installed LocalArtifactStore home/artifacts root; require concrete own-root files; permit deduplicated payload paths",
    "Before the same four GETs, audit both original synthetic artifact directory and every canonical payload path",
    "Keep previous assertions/volumes/guards, partial diagnostics and absence of latency metrics unchanged"]
write("PREPARED-v3.json", json.dumps(manifest, indent=2) + "\n")
print(json.dumps({name: sha(HERE / name) for name in ("worker_v3.py", "run_v3.py", "v3-counterparts.diff", "PREPARED-v3.json")}, indent=2))
