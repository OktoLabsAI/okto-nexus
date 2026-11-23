"""Bounded detached work for a disposable Codex MCP test."""
from pathlib import Path
from subprocess import DEVNULL, Popen
import os
import sys
from time import monotonic, sleep
from typing import Literal

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "nexus-gate-release.release"
STARTED = ROOT / "background-started"
DONE = ROOT / "background-completed"
MARKER = b"NEXUS_SESSION_GATE_OPEN\n"

if __name__ == "__main__" and sys.argv[1:] == ["--background-worker"]:
    with STARTED.open("x", encoding="ascii") as evidence:
        evidence.write(str(os.getpid()) + "\n")
    until = monotonic() + 230
    while monotonic() < until:
        if RELEASE.is_file() and not RELEASE.is_symlink() and RELEASE.read_bytes() == MARKER:
            with DONE.open("x", encoding="ascii") as evidence:
                evidence.write(str(os.getpid()) + "\n")
            sys.exit(0)
        sleep(.05)
    sys.exit(124)

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("Nexus disposable background gate")
children = []


@server.tool(annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=False,
))
def wait_for_marker(scenario: Literal["release"]) -> str:
    """Start the bounded reader process and return while it waits for a fixed marker."""
    if children:
        raise RuntimeError("The fixture admits only one background job")
    child = Popen([sys._base_executable, "-I", "-B", str(Path(__file__).resolve()), "--background-worker"],
                  stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, cwd=ROOT)
    children.append(child)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Background worker exited early")
        try:
            if int(STARTED.read_text(encoding="ascii")) == child.pid:
                return "NEXUS_BACKGROUND_RUNNING"
        except (OSError, ValueError):
            pass
        sleep(.04)
    raise RuntimeError("Background worker failed to start")


if __name__ == "__main__":
    server.run(transport="stdio")
