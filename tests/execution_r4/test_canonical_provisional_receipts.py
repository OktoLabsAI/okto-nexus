"""A live producer owns its provisional journal state until it settles."""
import asyncio
import time
from nexus_connector_core import CoreError
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


def test_live_open_prewrite_refusal_is_not_preceded_by_uncertain_recovery_receipt(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    first = admit(setup, binding, 'healthy-before-provisional', 'runtime.start', new_session=True)
    wait_receipt(setup, first)
    entered, release = asyncio.Event(), asyncio.Event()
    async def refuse(*args, **kwargs):
        entered.set()
        await release.wait()
        raise CoreError('PROFILE_DRIFT', 'environment', retry_safe=True, possible_effect=False)
    with monkeypatch.context() as patch:
        patch.setattr(native, 'open', refuse)
        rejected = admit(setup, binding, 'held-refusal', 'runtime.start', new_session=True)
        try:
            deadline = time.monotonic() + 10
            while not entered.is_set():
                assert time.monotonic() < deadline
                time.sleep(.02)
            # Force a live observation of the real Core SUBMISSION_STARTED
            # journal before the factory provides durable no-effect proof.
            client.portal.call(lambda: owner._recover_publications(agent_id='subject'))
        finally:
            client.portal.call(release.set)
        failed = wait_receipt(setup, rejected, stages=('FAILED',))
        assert failed['possible_effect'] is False and failed['retry_safe'] is True
        deadline = time.monotonic() + 10
        while rejected['session_id'] in owner.sessions:
            assert time.monotonic() < deadline
            time.sleep(.02)
    assert 'subject' not in owner.agents.blocked and owner.failure is None
    assert not native.native.stopped
    sent = admit(setup, binding, 'healthy-after-provisional', 'turn.submit', session_id=first['session_id'], text='Still available')
    wait_receipt(setup, sent)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
