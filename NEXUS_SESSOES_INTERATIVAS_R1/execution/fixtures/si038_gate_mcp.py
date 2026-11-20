"""Read a known marker in a disposable session-qualification workspace."""

from pathlib import Path
from time import monotonic, sleep
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("Nexus disposable session gate")
MARKER = b"NEXUS_SESSION_GATE_OPEN\n"


@server.tool(annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
def wait_for_marker(scenario: Literal["release", "timeout"]) -> str:
    """Wait for the known local qualification marker. The tool performs no writes."""
    workspace = Path(__file__).resolve().parent
    marker = workspace / ("nexus-gate-" + scenario + ".release")
    until = monotonic() + (180 if scenario == "release" else 3)
    while monotonic() < until:
        if marker.is_symlink():
            return "NEXUS_GATE_REJECTED"
        try:
            with marker.open("rb") as descriptor:
                if descriptor.read(len(MARKER) + 1) != MARKER:
                    return "NEXUS_GATE_REJECTED"
        except FileNotFoundError:
            sleep(0.1)
        else:
            return "NEXUS_GATE_RELEASED"
    return "NEXUS_GATE_TIMED_OUT"


if __name__ == "__main__":
    server.run(transport="stdio")
