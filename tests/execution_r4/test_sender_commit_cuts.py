"""T24: reservation/send/owner-release commits cannot authorize a replay."""
import json

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import release_dispatch_owner
from okto_nexus.application.execution_dispatch import (
    DispatchReservation, begin_execution_send, reserve_execution_dispatch, release_unsent_dispatch,
)
from test_dispatch_pump import owner
from test_handoff_creation_commit_cuts import CommitCut


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        return {table: [dict(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in ('execution_dispatch_outbox', 'execution_operations', 'execution_sessions',
                              'execution_unsent_dispatch_proofs', 'execution_receipts')}


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('stage', ['reserve', 'begin_send', 'release_owner'])
def test_sender_commit_cut_recovers_unsent_or_retains_uncertainty(owner, boundary, stage):
    deps, app, access, _, _, channel, resolution, _ = owner
    factory = deps.connection_factory

    def reserve(cf):
        return reserve_execution_dispatch(cf, server_id=channel.server_id, executor_id=channel.executor_id,
                                          remote_ready=True, channel=channel)

    def begin(cf, reservation):
        return begin_execution_send(cf, reservation=reservation, remote_ready=True, channel=channel,
                                    access=access, fresh_publications=app.state.inventory_fresh_publications)

    reservation = reserve(factory) if stage != 'reserve' else None
    if stage == 'release_owner':
        begin(factory, reservation)
    before = snapshot(factory)
    cut = CommitCut(factory, boundary)
    with pytest.raises(OSError):
        if stage == 'reserve':
            reserve(cut)
        elif stage == 'begin_send':
            begin(cut, reservation)
        else:
            release_dispatch_owner(cut, channel=channel)
    assert cut.fired
    reopened = ConnectionFactory(deps.config)
    if boundary == 'rollback':
        assert snapshot(reopened) == before
    row = snapshot(reopened)['execution_dispatch_outbox'][0]
    assert row['operation_id'] == resolution['operation_id']
    if stage == 'reserve':
        if boundary == 'rollback':
            reservation = reserve(reopened)
        else:
            assert row['dispatch_state'] == 'RESERVED'
            assert reserve(reopened) is None
            reservation = DispatchReservation(channel.server_id, channel.executor_id,
                row['operation_id'], row['attempt_token'], row['attempt_no'],
                row['reservation_class'], row['reserved_bytes'],
                row['reservation_owner'], row['reservation_generation'])
        # This owner has not begun the send. Only its exact retained token can
        # release the reservation; operation identity and history stay intact.
        release_unsent_dispatch(reopened, reservation=reservation)
        replacement = reserve(reopened)
        assert replacement.operation_id == reservation.operation_id
        assert replacement.attempt_no == reservation.attempt_no + 1
        assert replacement.attempt_token != reservation.attempt_token
        release_unsent_dispatch(reopened, reservation=replacement)
        final = snapshot(reopened)
        assert final['execution_dispatch_outbox'][0]['dispatch_state'] == 'PENDING'
        assert not final['execution_receipts']
        return
    if stage == 'begin_send' and boundary == 'rollback':
        assert row['dispatch_state'] == 'RESERVED'
        begin(reopened, reservation)
    # Once SENDING may have committed, failure of its return path cannot be
    # converted into a no-effect fact. Owner loss retains the reconciliation
    # obligation even though this fixture never invokes a native provider.
    release_dispatch_owner(reopened, channel=channel)
    final = snapshot(reopened)
    row = final['execution_dispatch_outbox'][0]
    assert row['dispatch_state'] == 'RECONCILING'
    assert row['attempt_no'] == reservation.attempt_no and row['attempt_token'] == reservation.attempt_token
    assert row['reserved_bytes'] > 0
    assert json.loads(row['last_error'])['possible_effect'] is True
    assert final['execution_operations'][0]['admission_state'] == 'RECONCILING'
    assert not final['execution_receipts'] and not final['execution_unsent_dispatch_proofs']
    assert reserve(reopened) is None
