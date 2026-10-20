"""History/queue stalls must not prevent independent lease scheduling."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap import embedded_dispatch
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner


@pytest.mark.parametrize('blocked_phase', ['history', 'queue'])
def test_renewals_progress_while_maintenance_and_another_renewal_are_held(monkeypatch, blocked_phase):
    from okto_nexus.application import runtime_recovery

    async def scenario():
        entered, release = threading.Event(), threading.Event()
        slow_started, fast_finished, release_slow = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        async def tick():
            if blocked_phase == 'history':
                entered.set()
                await asyncio.to_thread(release.wait)

        def drain(_):
            if blocked_phase == 'queue':
                entered.set()
                release.wait()

        async def failed():
            raise AssertionError('Unrelated maintenance must not fail authority scheduling')

        async def renew(session_id, session):
            calls.append(session_id)
            if session_id == 'slow':
                slow_started.set()
                await release_slow.wait()
            else:
                fast_finished.set()
            session['renew_at'] = None

        owner = SimpleNamespace(
            _stopping=asyncio.Event(), failure=None, deps=None, renewals=set(),
            sessions={sid: {'scope': {'agent_id': sid}, 'renew_at': 0} for sid in ('slow', 'fast')},
            agents=SimpleNamespace(blocked=set(), tick=tick),
            capacity_publication=SimpleNamespace(tick=lambda: None),
            _renew_owned=renew, failed=failed,
        )
        monkeypatch.setattr(runtime_recovery, 'drain_pending', drain)
        maintenance = asyncio.create_task(EmbeddedDispatchOwner._maintain(owner))
        scheduler = None
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            scheduler = asyncio.create_task(EmbeddedDispatchOwner._maintain_leases(owner))
            await asyncio.wait_for(slow_started.wait(), 3)
            await asyncio.wait_for(fast_finished.wait(), 3)
            # Cross multiple scheduler ticks while the first renewal and the
            # maintenance phase remain held: neither may be duplicated.
            await asyncio.sleep(.2)
            assert not release.is_set() and not maintenance.done()
            assert calls == ['slow', 'fast']
            assert owner.failure is None
        finally:
            owner._stopping.set()
            release.set()
            release_slow.set()
            await asyncio.gather(maintenance, *([scheduler] if scheduler else []))
            await asyncio.gather(*tuple(owner.renewals))

    asyncio.run(scenario())


@pytest.mark.parametrize(('started', 'deadline', 'expected'), [
    (99.4, 101, 100),  # Little life remains after an expensive application.
    (99.9, 160, 129.9),  # Long grants retain the half-life safety margin.
    (99, 99.5, 100),  # An expired grant is never extended by scheduling.
])
def test_renewal_reserves_observed_application_cost(monkeypatch, started, deadline, expected):
    monkeypatch.setattr(embedded_dispatch.time, 'monotonic', lambda: 100)
    session = {'executor': SimpleNamespace(lease_request_started=started)}
    applied = SimpleNamespace(context=SimpleNamespace(lease_deadline_monotonic=deadline))
    EmbeddedDispatchOwner._schedule_renewal(None, session, applied)
    assert session['renew_at'] == pytest.approx(expected)
    assert applied.context.lease_deadline_monotonic == deadline
