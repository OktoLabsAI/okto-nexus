"""A transient candidate cleanup failure cannot abandon its retained owner."""
import asyncio
from types import SimpleNamespace

from okto_nexus.bootstrap.embedded_supervisor import EmbeddedRuntimeSupervisor


def test_shutdown_retries_same_candidate_after_cleanup_error():
    class Candidate:
        attempts = 0
        stopped = False
        def begin_shutdown(self):
            self.stopped = True
        async def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError('Transient inventory release failure')

    async def scenario():
        candidate = Candidate()
        supervisor = EmbeddedRuntimeSupervisor(SimpleNamespace(), SimpleNamespace())
        supervisor._candidate = candidate
        supervisor.begin_shutdown()
        supervisor.start()
        await asyncio.wait_for(supervisor.aclose(), 5)
        assert supervisor.drained and supervisor._candidate is None
        assert candidate.stopped and candidate.attempts == 2
    asyncio.run(scenario())
