"""Safe async shutdown locations for CI hangs; no local variables or payloads."""
import asyncio
from pathlib import Path
import sys


def task_locations():
    lines = []
    for task in asyncio.all_tasks():
        current, frames = task.get_coro(), []
        for _ in range(24):
            frame = getattr(current, 'cr_frame', None) or getattr(current, 'gi_frame', None)
            if frame is not None:
                frames.append(f'{Path(frame.f_code.co_filename).name}:{frame.f_lineno}:{frame.f_code.co_name}')
            current = getattr(current, 'cr_await', None) or getattr(current, 'gi_yieldfrom', None)
            if current is None:
                break
        lines.append(' -> '.join(frames))
    return '\n'.join(sorted(lines))


def install_shutdown_diagnostics(monkeypatch):
    from okto_nexus.bootstrap.server_shutdown import ServerShutdownCoordinator
    from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
    original_wait = ServerShutdownCoordinator.wait
    original_close = EmbeddedDispatchOwner._close

    async def observed_wait(self):
        task = asyncio.create_task(original_wait(self))
        while not task.done():
            await asyncio.wait((task,), timeout=15)
            if not task.done():
                print('SHUTDOWN_PENDING_TASKS\n' + task_locations(), file=sys.__stderr__, flush=True)
        return await task

    async def observed_close(self):
        try:
            return await original_close(self)
        except Exception as error:
            # Only code locations and exception type; never dump credentials,
            # native content, resource identifiers or arbitrary error messages.
            frame = error.__traceback__
            locations = []
            while frame is not None:
                locations.append(f'{Path(frame.tb_frame.f_code.co_filename).name}:{frame.tb_lineno}')
                frame = frame.tb_next
            signature = (type(error).__name__, tuple(locations))
            if getattr(self, '_test_shutdown_error', None) != signature:
                self._test_shutdown_error = signature
                print('SHUTDOWN_CLOSE_ERROR', *signature, file=sys.__stderr__, flush=True)
            raise

    monkeypatch.setattr(ServerShutdownCoordinator, 'wait', observed_wait)
    monkeypatch.setattr(EmbeddedDispatchOwner, '_close', observed_close)
