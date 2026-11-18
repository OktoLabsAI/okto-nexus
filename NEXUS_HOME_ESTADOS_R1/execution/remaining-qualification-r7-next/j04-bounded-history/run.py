"""PREPARED Root-gated single functional worker; no product import in host."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard(manifest):
    for mapping in (manifest["source_pins"], manifest["helper_sha256"]):
        assert all(sha(Path(path)) == expected for path, expected in mapping.items())
    ready = json.loads(Path(manifest["ready"]).read_text(encoding="utf-8"))
    assert sha(Path(manifest["ready"])) == manifest["ready_sha256"]
    assert sha(Path(ready["wheel"])) == ready["wheel_sha256"] == manifest["wheel_sha256"]
    assert ready["source_commit"] == manifest["source_commit"]
    prefix = Path(ready["python"]).parent.parent / "Lib/site-packages"
    assert len(manifest["payload_files"]) == ready["payload_files"] == 1031
    assert all(sha(prefix / name) == expected for name, expected in manifest["payload_files"].items())
    return {"source_pins": len(manifest["source_pins"]), "payload_files": 1031, "drift": []}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--gate", choices=["ROOT_APPROVED_J04_FUNCTIONAL"], required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    path = HERE / "PREPARED.json"
    assert sha(path) == args.manifest_sha256
    manifest = json.loads(path.read_text(encoding="utf-8"))
    before = guard(manifest)
    dataset = Path(manifest["original_dataset"])
    source = json.loads(dataset.read_text(encoding="utf-8"))
    owner = dataset.parent.resolve()
    assert json.loads((owner / ".hst-owned.json").read_text()) == {"root": str(owner), "kind": "hst-performance-synthetic-only"}
    case = next(case for case in source["cases"] if case["size"] == 100)
    assert source["workload"] == "J04-open-complement"
    seed = (owner / "seed-100-open/home").resolve()
    assert seed.is_relative_to(owner) and sha(seed / "nexus.db") == case["database_sha256"] == manifest["seed_database_sha256"]
    assert sha(dataset) == manifest["original_dataset_sha256"]
    # All source/precondition guards complete before allocating a clone/process.
    root = Path(tempfile.mkdtemp(prefix="nexus-hst-j04-functional-")).resolve()
    (root / ".j04-owned.json").write_text(json.dumps({"root": str(root), "kind": "j04-functional-synthetic-only"}), encoding="utf-8")
    shutil.copytree(seed, root / "home")
    assert sha(root / "home/nexus.db") == case["database_sha256"]
    (root / "cwd").mkdir()
    commands = load("j04_owned_commands", Path(manifest["command_helper"]))
    environment = load("j04_own_environment", Path(manifest["environment_helper"]))
    ready = json.loads(Path(manifest["ready"]).read_text())
    import time
    manager = commands.Commands(root, environment.environment(root), time.monotonic() + 180)
    failure = None
    forced = []
    try:
        manager.run("functional-history", [ready["python"], "-I", "-B", "-X", "utf8", str(HERE / "worker.py"),
            "--manifest", str(path), "--manifest-sha256", args.manifest_sha256, "--root", str(root)], timeout=180)
    except BaseException as error:  # noqa: BLE001 -- finally retains cleanup and guards, no retry.
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        if manager.remaining():
            forced = manager.contain()["forced_births"]
        after = guard(manifest)
        assert sha(dataset) == manifest["original_dataset_sha256"]
        assert sha(seed / "nexus.db") == manifest["seed_database_sha256"]
        final = {"failure": failure, "before": before, "after": after, "commands": manager.commands,
            "remaining": manager.remaining(), "forced": forced, "root": str(root), "provider_invocations": 0,
            "latencies_collected": False, "original_seed_unchanged": True}
        (root / "final.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(final), flush=True)
    return int(bool(failure or forced or manager.remaining()))


if __name__ == "__main__":
    raise SystemExit(main())
