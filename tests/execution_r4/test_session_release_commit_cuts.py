"""T24: release acceptance commits projections before acknowledging the host."""
import json

import pytest
from nexus_connector_core import encode_r4_frame
from nexus_connector_core.session_release import SESSION_RELEASE_REVISION, session_release_accepted

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.bootstrap.execution_authority import build_execution_access, ExecutionToolDependencies
from okto_nexus.errors import OktoNexusError
from test_handoff_creation_commit_cuts import CommitCut
from test_live_session_release import evidence
from test_session_containment_obligation import active_lease


TABLES = ('execution_sessions', 'execution_session_containment', 'execution_receipts',
          'execution_event_watermarks', 'execution_operations', 'execution_dispatch_outbox',
          'execution_delivery_releases', 'handoffs', 'runtime_handoff_bindings')


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        return {table: [dict(row) for row in uow.connection.execute(
            'SELECT * FROM ' + table + ' ORDER BY rowid')] for table in TABLES}


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
def test_release_commit_loss_preserves_original_proof_and_idempotent_ack(tmp_path, monkeypatch, boundary):
    with active_lease(tmp_path, monkeypatch, extra_capabilities=(SESSION_RELEASE_REVISION,)) as values:
        setup, ws, channel, opened, renewal = values
        deps, _, access, operator, grant, *_ = setup
        request, _ = evidence(setup, channel, opened)
        access.revoke(operator, grant_id=grant['grant_id'])
        ws.send_text(encode_r4_frame(renewal).decode())
        assert ws.receive_json()['type'] == 'lease.denied'
        before = snapshot(deps.connection_factory)
        cut = CommitCut(deps.connection_factory, boundary)
        service = build_execution_access(ExecutionToolDependencies(deps, cut)).session_release
        with pytest.raises(OSError, match='canonical commit'):
            service.accept(request, channel=channel)
        assert cut.fired
        reopened = ConnectionFactory(deps.config)
        observed = snapshot(reopened)
        if boundary == 'rollback':
            assert observed == before
        else:
            assert observed['execution_sessions'][0]['lifecycle_state'] == 'CLOSED'
            assert observed['execution_session_containment'][0]['state'] == 'RELEASED'
        rebuilt = build_execution_access(ExecutionToolDependencies(deps, reopened)).session_release
        assert rebuilt.accept(request, channel=channel) == session_release_accepted(request)
        settled = snapshot(reopened)
        session, = settled['execution_sessions']
        assert (session['lifecycle_state'], session['lease_state']) == ('CLOSED', 'CLOSED')
        obligation, = settled['execution_session_containment']
        assert obligation['state'] == 'RELEASED'
        assert json.loads(obligation['release_proof_json'])['request'] == request
        assert obligation['released_at'] is not None
        for table in TABLES[2:]:
            assert settled[table] == before[table], table
        if boundary == 'lost_reply':
            assert settled == observed
        assert rebuilt.accept(request, channel=channel) == session_release_accepted(request)
        with pytest.raises(OktoNexusError):
            rebuilt.accept(dict(request, release_id='replacement'), channel=channel)
        assert snapshot(reopened) == settled
