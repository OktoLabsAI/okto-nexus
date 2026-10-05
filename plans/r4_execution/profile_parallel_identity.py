"""Profile source parallel passive discovery without launching a native provider."""
import cProfile
import hashlib
import tomllib
import json
import os
from pathlib import Path
import pstats
import time
import sys
CORE_SOURCE = Path(__file__).resolve().parents[3] / "okto-nexus-connector-core/src"
sys.path.insert(0, str(CORE_SOURCE))
from nexus_connector_core import discover_installations

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "plans/r4_execution/evidence"
node = Path("C:/Program Files/nodejs/node.exe")
install = Path.home() / ".pi/agent/install"
assert node.is_file() and install.is_dir()
profile = cProfile.Profile()
started = time.monotonic()
profile.enable()
try:
    inventory = discover_installations(
        trusted_roots=(node.parent, install),
        path_env=str(node.parent) + os.pathsep + os.environ.get("PATH", ""),
        pi_install_root=install, pi_node=node)
finally:
    profile.disable()
    elapsed = time.monotonic() - started
    stats = pstats.Stats(profile)
    rows = [dict(file=Path(key[0]).name, line=key[1], function=key[2],
        calls=value[1], self_seconds=value[2], cumulative_seconds=value[3])
        for key, value in stats.stats.items()]
    rows.sort(key=lambda row: row["cumulative_seconds"], reverse=True)
    report = dict(core_version=tomllib.loads((CORE_SOURCE.parent / "pyproject.toml").read_text())["project"]["version"],
        elapsed_seconds=elapsed, top_functions=rows[:45],
        command_scope="Modified Core source, same approved Pi/Node roots as the public campaign, passive reads only.",
        source=str(CORE_SOURCE), profiler_limit="Caller thread only; worker digest bodies are not profiled.",
        source_sha256=hashlib.sha256((CORE_SOURCE / "nexus_connector_core/build_identity.py").read_bytes()).hexdigest())
    if "inventory" in globals():
        report["candidates"] = [dict(adapter_id=c.adapter_id, version=c.version,
            build_identity=c.build_identity, architecture=c.architecture) for c in inventory.candidates]
    (OUT / "parallel-identity-source-profile.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "top_functions"}, indent=2))
