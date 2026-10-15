"""Release history workers are bounded, deduplicated, retained and independent."""
import asyncio
import json
import threading
from importlib.resources import files

import pytest
from nexus_connector_core.session_release import session_release_accepted
from okto_nexus.adapters.inbound.http.session_release_owner import SessionReleaseOwner


def sample():
    return json.loads(files('nexus_connector_core').joinpath(
        'contracts','session_release','v1','fixtures.json').read_bytes())['valid'][0]['frame']


@pytest.mark.asyncio
async def test_release_worker_capacity_and_cancelled_stop_keep_original_producer():
    entered, release = threading.Event(), threading.Event()
    calls, replies = [], asyncio.Queue()
    def validate(frame):
        calls.append(frame)
        entered.set()
        assert release.wait(5)
        return session_release_accepted(frame)
    owner = SessionReleaseOwner(validate=validate, send=replies.put, max_pending=1)
    original = sample()
    try:
        await owner.submit(original)
        assert await asyncio.to_thread(entered.wait, 2)
        await owner.submit(original)
        other = dict(original, release_id='other')
        await owner.submit(other)
        assert (await replies.get())['type'] == 'session.release.deferred'
        assert len(owner.pending) == 1 and calls == [original]
        stopped = asyncio.create_task(owner.stop())
        await asyncio.sleep(0)
        stopped.cancel()
        with pytest.raises(asyncio.CancelledError): await stopped
        assert len(owner.pending) == 1
        release.set()
        await owner.stop()
        assert not owner.pending and calls == [original] and replies.empty()
    finally:
        release.set()
        await owner.stop()
