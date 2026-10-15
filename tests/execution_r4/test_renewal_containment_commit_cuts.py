"""T24: a renewal denial's commit never implies physical resource release."""
import json

import pytest
from nexus_connector_core import encode_r4_frame

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_session_containment import SqliteSessionContainmentRepository
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.application.execution_session_containment import ExecutionSessionContainment
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.errors import OktoNexusError
from test_handoff_creation_commit_cuts import CommitCut
from test_session_containment_obligation import active_lease


TABLES = ('execution_session_containment', 'execution_sessions', 'execution_leases',
          'execution_operations', 'execution_dispatch_outbox', 'execution_receipts')


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        return {table: [dict(row) for row in uow.connection.execute(
            'SELECT * FROM ' + table + ' ORDER BY rowid')] for table in TABLES}


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('stage', ['before_grant', 'before_applied'])
def test_renewal_denial_commit_reopens_same_obligation_without_release(tmp_path, monkeypatch, boundary, stage):
    with active_lease(tmp_path, monkeypatch) as (setup, ws, channel, opened, renewal):
        deps, app, access, operator, grant, *_ = setup
        if stage == 'before_applied':
            ws.send_text(encode_r4_frame(renewal).decode())
            issued = ws.receive_json()
            assert issued['type'] == 'lease.granted' and issued['lease_serial'] == 2
        access.revoke(operator, grant_id=grant['grant_id'])
        leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
            fresh_publications=app.state.inventory_fresh_publications)
        with pytest.raises(OktoNexusError):
            leases.issue(renewal, channel=channel)
        before = snapshot(deps.connection_factory)
        cut = CommitCut(deps.connection_factory, boundary)
        service = ExecutionSessionContainment(factory=cut,
            repository=SqliteSessionContainmentRepository(), clock=deps.clock)
        with pytest.raises(OSError, match='canonical commit'):
            service.denied(renewal, channel=channel)
        assert cut.fired
        reopened = ConnectionFactory(deps.config)
        observed = snapshot(reopened)
        if boundary == 'rollback':
            assert observed == before
        else:
            assert len(observed['execution_session_containment']) == 1
        replacement = ExecutionSessionContainment(factory=reopened,
            repository=SqliteSessionContainmentRepository(), clock=deps.clock)
        assert replacement.denied(renewal, channel=channel)
        settled = snapshot(reopened)
        obligation, = settled['execution_session_containment']
        assert obligation['state'] == 'REQUESTED'
        assert obligation['release_proof_json'] is None and obligation['released_at'] is None
        assert json.loads(obligation['request_json']) == renewal
        assert obligation['opening_operation_id'] == opened['operation_id']
        assert obligation['opening_intent_hash'] == opened['intent_hash']
        for table in TABLES[1:]:
            assert settled[table] == before[table], table
        if boundary == 'lost_reply':
            assert settled == observed
        assert replacement.denied(renewal, channel=channel)
        assert snapshot(reopened) == settled
        # Restoring configuration alone cannot release an already contained session.
        with reopened.unit_of_work() as uow:
            uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=NULL WHERE grant_id=?',
                                   (grant['grant_id'],))
        fresh_access = build_execution_access(deps)
        fresh_access.session_containment = replacement
        retry = ExecutionLeaseService(factory=reopened, access=fresh_access,
            fresh_publications=app.state.inventory_fresh_publications)
        with pytest.raises(OktoNexusError, match='confirmed resource release'):
            retry.issue(renewal, channel=channel)
