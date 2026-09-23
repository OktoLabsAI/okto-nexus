"""Compare live MCP schemas against a Git baseline without using personal config."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


RUNNER = '''
import asyncio, json, sys
from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server, SURFACE_REVISION
from okto_nexus.adapters.inbound.mcp.surface_metrics import measure_resident_surface
async def run():
    results = {}
    for enabled in (False, True):
        deps = bootstrap({}, ["--home", sys.argv[1] + str(enabled)])
        deps.config.feature_harness_integrations = enabled
        server = create_server(deps)
        tools = await server.list_tools()
        results[str(enabled)] = dict(await measure_resident_surface(server),
            tool_count=len(tools), harness_tools=sorted(t.name for t in tools if t.name.startswith("harness_")))
    print(json.dumps(dict(surface_revision=SURFACE_REVISION, measurements=results)))
asyncio.run(run())
'''


def main():
    repo = Path(__file__).resolve().parents[2]
    baseline = sys.argv[1]
    python = (repo / ".venv/Scripts/python.exe").resolve()
    with tempfile.TemporaryDirectory(prefix="nexus-surface-") as directory:
        root = Path(directory)
        archive = root / "baseline.zip"
        with archive.open("wb") as output:
            subprocess.run(["git", "archive", "--format=zip", baseline, "src"], cwd=repo, stdout=output, check=True)
        old = root / "baseline"
        with zipfile.ZipFile(archive) as snapshot:
            snapshot.extractall(old)
        results = {"baseline_sha": baseline, "current_parent": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()}
        for label, source in (("baseline", old / "src"), ("worktree", repo / "src")):
            env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
            env.update(PYTHONPATH=str(source), HOME=str(root), USERPROFILE=str(root), PYTHONIOENCODING="utf-8")
            result = subprocess.run([str(python), "-c", RUNNER, str(root / (label + "-home-"))],
                cwd=root, env=env, text=True, encoding="utf-8", capture_output=True, check=True)
            results[label] = json.loads(result.stdout)
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
