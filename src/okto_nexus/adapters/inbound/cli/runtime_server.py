"""Keep the Server transport alive until its owned shutdown has drained."""
import asyncio
import logging

import uvicorn


class RuntimeServer(uvicorn.Server):
    def __init__(self, config):
        super().__init__(config)
        self._runtime_loop = None
        self._signal_shutdown_task = None
        self._serving_runtime = False

    async def serve(self, sockets=None):
        self._runtime_loop = asyncio.get_running_loop()
        self._serving_runtime = True
        try:
            await super().serve(sockets=sockets)
        finally:
            self._serving_runtime = False
            if self._signal_shutdown_task is not None:
                await asyncio.shield(self._signal_shutdown_task)
            self._runtime_loop = None

    def handle_exit(self, sig, frame):
        # Uvicorn's default handler stops accepting HTTP immediately and makes
        # a second SIGINT force exit. A signal here requests the same retained
        # shutdown as the administrative API; repetition is observation only.
        if self._runtime_loop is not None:
            self._runtime_loop.call_soon_threadsafe(self._start_signal_shutdown)

    def _start_signal_shutdown(self):
        if self._signal_shutdown_task is None:
            self._signal_shutdown_task = asyncio.create_task(
                self._shutdown_from_signal(), name="server-signal-shutdown")

    async def _shutdown_from_signal(self):
        logger = logging.getLogger(__name__)
        # A signal can arrive during ASGI startup, before the coordinator is
        # installed. Wait for that owner rather than disposing its event loop.
        while self._serving_runtime:
            owner = getattr(self.config.app.state, "runtime_shutdown", None)
            if owner is None:
                await asyncio.sleep(.01)
                continue
            report = await owner.request()
            logger.info("Server shutdown state: %s", report["state"])
            await owner.wait()
            return
