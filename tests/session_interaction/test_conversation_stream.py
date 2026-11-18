"""The live conversation only announces exact committed cursor changes."""

import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.http.dashboard_session_stream import _follow
from okto_nexus.errors import ErrorCode, OktoNexusError


def frame(message):
    event, data, *_ = message.splitlines()
    return event.removeprefix('event: '), json.loads(data.removeprefix('data: '))


def request_for(*, signed_in=True):
    login = SimpleNamespace(active=True)
    state = SimpleNamespace(sse_poll_seconds=0, sse_ping_seconds=60,
                            operator_auth=SimpleNamespace(resolve=lambda _token: login.active))
    return SimpleNamespace(app=SimpleNamespace(state=state), state=SimpleNamespace(operator_session=signed_in),
                           cookies={'nexus_operator_session': 'fixture'}), login


@pytest.mark.asyncio
async def test_stream_coalesces_idle_rounds_and_rechecks_the_original_login():
    request, login = request_for()
    initial = {'version': 1, 'scope': {'session_id': 'fixture', 'session_owner_generation': 3},
               'stream_epoch': 'epoch-one', 'committed_contiguous': 8, 'gap_pending': False}
    changed = {**initial, 'committed_contiguous': 13}
    reads = iter([initial, initial, changed])
    events = _follow(request, lambda: next(reads), initial)
    assert frame(await anext(events)) == ('conversation-position', initial)
    assert frame(await anext(events)) == ('conversation-position', changed)
    login.active = False
    # A committed snapshot read still succeeds with the captured context.
    # The cookie check must happen before the next frame is disclosed.
    assert frame(await anext(events)) == ('conversation-unavailable', {'version': 1, 'reason': 'authorization_lost'})
    with pytest.raises(StopAsyncIteration):
        await anext(events)


@pytest.mark.asyncio
@pytest.mark.parametrize(('code', 'reason'), [
    (ErrorCode.NOT_FOUND, 'scope_changed'),
    (ErrorCode.PERMISSION_DENIED, 'authorization_lost'),
    (ErrorCode.DB_ERROR, 'temporarily_unavailable'),
])
async def test_stream_ends_with_a_bounded_reason_when_the_exact_view_is_lost(code, reason):
    request, _ = request_for(signed_in=False)
    initial = {'version': 1, 'scope': {'session_id': 'fixture', 'session_owner_generation': 3},
               'stream_epoch': 'epoch-one', 'committed_contiguous': 8, 'gap_pending': False}

    def read():
        raise OktoNexusError(code, 'Internal details are private.', {})

    events = _follow(request, read, initial)
    assert frame(await anext(events)) == ('conversation-position', initial)
    assert frame(await anext(events)) == ('conversation-unavailable', {'version': 1, 'reason': reason})
    with pytest.raises(StopAsyncIteration):
        await anext(events)
