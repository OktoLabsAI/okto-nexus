"""Test-only Server process for real remote provider acceptance."""
import argparse
import asyncio
import sys

import uvicorn

from nexus_connector_core import R4_PREVIEW_REVISION
from okto_nexus.adapters.inbound.http import connections_v1, executor_link, runtime_v1
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


async def serve(home, port):
    info = executor_link.protocol_info()
    assert info["remote_execution_ready"] is True
    assert info["nxl_accepted"] == [R4_PREVIEW_REVISION]
    assert connections_v1.protocol_info() == runtime_v1.protocol_info() == info
    deps = bootstrap({}, ["--home", home, "--feature-harness-integrations", "true",
                          "--feature-hitl", "true"])
    origin = "http://127.0.0.1:" + str(port)
    app = build_app(deps, runtime_owner_api_url=origin)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
        log_level="error", access_log=False, timeout_graceful_shutdown=5))
    async def stop_control():
        await asyncio.to_thread(sys.stdin.readline)
        server.should_exit = True
    control = asyncio.create_task(stop_control())
    try:
        await server.serve()
    finally:
        control.cancel()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    asyncio.run(serve(args.home, args.port))
