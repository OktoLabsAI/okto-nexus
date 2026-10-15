"""T24: canonical creation/unblocking never leaves a partial competitive notice."""
from contextlib import contextmanager

import pytest

from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.errors import OktoNexusError
from test_handoff_dependencies import make_env


TABLES = ('handoffs', 'handoff_dependencies', 'handoff_authorization_receipts',
          'execution_handoff_origins', 'events', 'messages', 'message_deliveries',
          'runtime_handoff_notifications', 'handoff_runtime_schedule',
          'runtime_pending_deliveries', 'delivery_outbox', 'execution_operations')


def snapshot(factory):
    with factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute(
            'SELECT * FROM ' + table + ' ORDER BY rowid')] for table in TABLES}


class CommitCut:
    def __init__(self, factory, boundary):
        self.factory, self.boundary, self.fired = factory, boundary, False
        self.handoff_ids = []

    def __getattr__(self, name):
        return getattr(self.factory, name)

    @contextmanager
    def unit_of_work(self, **kwargs):
        cut = False
        with self.factory.unit_of_work(**kwargs) as uow:
            before = uow.connection.total_changes
            yield uow
            cut = not self.fired and kwargs.get('write') is not False and uow.connection.total_changes > before
            if cut:
                self.fired = True
                self.handoff_ids = [row[0] for row in uow.connection.execute('SELECT handoff_id FROM handoffs ORDER BY rowid')]
                if self.boundary == 'rollback':
                    raise OSError('Before canonical commit')
        if cut and self.boundary == 'lost_reply':
            raise OSError('After canonical commit')


def create(service, root, *, depends_on=None):
    return service.handoff_create(project_root=root, from_agent_id='alpha',
        target={'strategy': 'broadcast'}, visibility='eligible',
        payload='Private task: not notification text', depends_on=depends_on)


def assert_competitive(factory, handoff_id, event):
    with factory.unit_of_work(write=False) as uow:
        notices = uow.connection.execute('SELECT n.runtime_route,m.body,d.status,d.consumer_kind,n.recipient_agent_id '
            'FROM runtime_handoff_notifications n JOIN messages m USING(message_id) '
            'JOIN message_deliveries d USING(message_id) '
            'WHERE n.handoff_id=? AND n.event_type=?', (handoff_id, event)).fetchall()
        # Bootstrap also registers operator; preserve its ordinary MCP inbox.
        assert len(notices) == 3
        assert {row[4] for row in notices} == {'beta', 'gamma', 'operator'}
        assert all(row[0] == 'competitive' and 'Private task' not in row[1]
                   and row[2:4] == ('unread', None) for row in notices)
        agenda = uow.connection.execute('SELECT claim_generation,state FROM handoff_runtime_schedule '
            'WHERE handoff_id=?', (handoff_id,)).fetchall()
        assert [tuple(row) for row in agenda] == [(0, 'PENDING')]
        for table in ('runtime_pending_deliveries', 'delivery_outbox', 'execution_operations'):
            assert uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('stage', ['create', 'unblock'])
def test_canonical_notice_commit_cut_recovers_without_partial_or_duplicate_delivery(tmp_path, boundary, stage):
    deps, _, root, _ = make_env(tmp_path)
    service = build_service(deps)
    if stage == 'unblock':
        parent = create(service, root)['handoff_id']
        child = create(service, root, depends_on=[parent])['handoff_id']
        claimed = service.handoff_claim(project_root=root, handoff_id=parent, agent_id='beta')
        assert_competitive(deps.connection_factory, child, 'handoff.created')
        complete = dict(project_root=root, handoff_id=parent, agent_id='beta',
                        claim_epoch=claimed['claim_epoch'], result='Dependency done')
        action = lambda: service.handoff_complete(**complete)
    else:
        action = lambda: create(service, root)
    before = snapshot(deps.connection_factory)
    fault = CommitCut(deps.connection_factory, boundary)
    service._cf = fault
    with pytest.raises(OSError):
        action()
    assert fault.fired

    # Reopen through a fresh factory/service; no cached transaction or reply.
    recovered = build_service(deps)
    recovered._cf = ConnectionFactory(deps.config)
    persisted = snapshot(recovered._cf)
    if boundary == 'rollback':
        assert persisted == before
    if stage == 'create':
        if boundary == 'rollback':
            child = create(recovered, root)['handoff_id']
        else:
            child = fault.handoff_ids[-1]
            # Creation has no public idempotency key. Recover the committed
            # object by query, not by issuing a second create request.
            available = recovered.handoff_list_available(project_root=root, agent_id='beta')
            assert [h['handoff_id'] for h in available['handoffs']] == [child]
        assert_competitive(recovered._cf, child, 'handoff.created')
        with recovered._cf.unit_of_work(write=False) as uow:
            for table in ('handoffs', 'execution_handoff_origins', 'handoff_authorization_receipts'):
                assert uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 1
            assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.created'").fetchone()[0] == 1
        return

    if boundary == 'rollback':
        recovered.handoff_complete(**complete)
    settled = snapshot(recovered._cf)
    with pytest.raises(OktoNexusError):
        recovered.handoff_complete(**complete)
    assert snapshot(recovered._cf) == settled
    assert_competitive(recovered._cf, child, 'handoff.unblocked')
    with recovered._cf.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?',
            (parent,)).fetchone()[:] == ('COMPLETED', 1)
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.unblocked'").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.completed'").fetchone()[0] == 1
