"""Static immutable counterpart only; never allocate/import app or run a worker."""
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


old = (HERE / "worker.py").read_text(encoding="utf-8")
assert old.count(', "quick": "all"') == 2
new = old.replace(', "quick": "all"', '')
needle = '    reads = []\n    try:\n'
assert new.count(needle) == 1
new = new.replace(needle, '    reads = []\n    instrumentation = None\n    try:\n')
needle = '''                    assert response.status_code == 200, (path, response.status_code)
                    assert MARKER.encode() not in response.content
                    body = response.json().get("data", response.json())
                    reads.append({"path": path, "bytes": len(response.content), "response_sha256": hashlib.sha256(response.content).hexdigest(), "item_count": len(body.get("items", [])), "total": body.get("total"), "has_more": body.get("has_more")})
'''
replacement = '''                    read = {"path": path, "http_status": response.status_code, "bytes": len(response.content),
                        "response_sha256": hashlib.sha256(response.content).hexdigest()}
                    reads.append(read)
                    assert response.status_code == 200, (path, response.status_code)
                    assert MARKER.encode() not in response.content
                    body = response.json().get("data", response.json())
                    read.update(item_count=len(body.get("items", [])), total=body.get("total"), has_more=body.get("has_more"))
'''
assert new.count(needle) == 1
new = new.replace(needle, replacement)
needle = '''    finally:
        deps.connection_factory.close()


def main():'''
replacement = '''    finally:
        try:
            deps.connection_factory.close()
        finally:
            # Diagnostic only: keep partial observations on any assertion/error,
            # without completing, weakening or replaying the original checks.
            save(home.parent / "partial-read-diagnostics.json", {"reads": reads,
                "instrumentation": instrumentation, "latencies_collected": False})


def main():'''
assert new.count(needle) == 1
new = new.replace(needle, replacement)
ast.parse(new)
write("worker_v2.py", new)
old_runner = (HERE / "run.py").read_text(encoding="utf-8")
runner = old_runner.replace('HERE / "PREPARED.json"', 'HERE / "PREPARED-v2.json"').replace('HERE / "worker.py"', 'HERE / "worker_v2.py"')
ast.parse(runner)
write("run_v2.py", runner)
diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="worker.py", tofile="worker_v2.py"))
diff += "".join(difflib.unified_diff(old_runner.splitlines(True), runner.splitlines(True), fromfile="run.py", tofile="run_v2.py"))
write("v2-counterparts.diff", diff)
manifest = json.loads((HERE / "PREPARED.json").read_text(encoding="utf-8"))
for name in ("worker_v2.py", "run_v2.py", "prepare_v2.py", "v2-counterparts.diff"):
    manifest["helper_sha256"][str(HERE / name)] = sha(HERE / name)
manifest["antecedent_attempt1"] = {"qualification": "attempt1/qualification.json", "sha256": sha(HERE / "attempt1/qualification.json"),
    "status": "INCOMPLETE_RUNNER_PRECONDITION", "original_worker_sha256": sha(HERE / "worker.py")}
manifest["variant_delta"] = ["Only remove unsupported quick from two legacy results GETs", "Export partial reads and row instrumentation in finally, including a failed HTTP response's status/hash/size", "All original volumes/assertions/guards remain; no new latitude or latency metrics"]
write("PREPARED-v2.json", json.dumps(manifest, indent=2) + "\n")
print(json.dumps({name: sha(HERE / name) for name in ("worker_v2.py", "run_v2.py", "v2-counterparts.diff", "PREPARED-v2.json")}, indent=2))
