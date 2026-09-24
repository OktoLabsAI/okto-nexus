"""Alternate isolated immutable before/after benchmark processes on one host."""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import zipfile


def percentiles(values):
    values = sorted(values)
    return {"n": len(values), "mean": sum(values)/len(values),
        **{f"p{p}": values[math.ceil(len(values)*p/100)-1] for p in (50, 95, 99)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    original = "d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397"
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    variants = {"original": original, "current": current}
    roots = {}
    for label, sha in variants.items():
        root = repo / ".git" / ("pr34-benchmark-" + sha[:12])
        root.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(subprocess.check_output(["git", "archive", "--format=zip", sha], cwd=repo))) as archive:
            for name in archive.namelist():
                assert (root/name).resolve().is_relative_to(root.resolve())
            archive.extractall(root)
        roots[label] = root
    campaign = Path(__file__).with_name("runtime_comparison_benchmark.py")
    peer = roots["current"] / "tests/test_harness_codex_connector.py"
    result = {"status": "RUNNING", "versions": variants, "order": ["original", "current", "current", "original", "original", "current"],
        "samples_per_round": 40, "warmup_per_round": 5, "rounds": [],
        "benchmark_sha256": hashlib.sha256(campaign.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "percentile_method": "nearest rank; no dropped outliers; three isolated rounds per revision"}
    env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    try:
        for index, label in enumerate(result["order"]):
            output = args.output.with_name(args.output.stem + f"-{index}-{label}.json")
            log = output.with_suffix(".log")
            with log.open("w", encoding="utf-8") as sink:
                completed = subprocess.run([sys.executable, "-X", "utf8", str(campaign), str(roots[label]), str(peer), variants[label], str(output)],
                    cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT, timeout=180,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            assert completed.returncode == 0, log.read_text(encoding="utf-8")[-4000:]
            record = json.loads(output.read_text(encoding="utf-8"))
            assert record["status"] == "PASS" and len(record["samples"]) == 40 and record["owned_peers_stopped"] == 1
            result["rounds"].append({"label": label, "index": index, "evidence": record})
            print(json.dumps({"round": index, "label": label, "status": "PASS"}), flush=True)
        first = result["rounds"][0]["evidence"]
        for row in result["rounds"]:
            for field in ("peer_sha256", "benchmark_sha256", "dependencies", "python", "platform", "sqlite_settings", "local_open"):
                assert row["evidence"][field] == first[field], field
        result["metrics"] = {}
        for label in variants:
            samples = [s for r in result["rounds"] if r["label"] == label for s in r["evidence"]["samples"]]
            result["metrics"][label] = {field: percentiles([s[field] for s in samples]) for field in ("admission_ms", "persisted_terminal_ms")}
            result["metrics"][label]["components"] = {c: {"total_ms_per_turn": percentiles([s["components"][c]["total_ms"] for s in samples]),
                "calls_per_turn": percentiles([s["components"][c]["count"] for s in samples])}
                for c in ("fsync", "authentication", "runtime_policy")}
        result["status"] = "PASS"
    except BaseException as exc:
        result["status"] = "FAIL"
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)[:4000]}
        raise
    finally:
        args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
