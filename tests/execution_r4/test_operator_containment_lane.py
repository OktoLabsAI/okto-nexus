"""Containment retains the bound remote transport's identity and expiry fences."""
from datetime import datetime

import pytest

from test_open_bootstrap import opening
from okto_nexus.application.execution_leases import require_execution_lane
from okto_nexus.errors import OktoNexusError


@pytest.mark.parametrize('fault', [None, 'revoked', 'expired', 'ticket_expired', 'connection', 'generation', 'agent', 'scope'])
def test_operator_containment_never_replaces_transport_authority(opening, fault):
    deps, _, _, _, _, channel, resolution, _ = opening
    scope = resolution['scope']
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE execution_control_lanes SET state='DISCONNECTED'")
        if fault == 'revoked':
            conn.execute("UPDATE execution_link_tickets SET revoked_at='fixture' WHERE binding_id IS NOT NULL")
        elif fault == 'expired':
            conn.execute("UPDATE execution_control_lanes SET expires_at='2000-01-01T00:00:00Z'")
        elif fault == 'ticket_expired':
            conn.execute("UPDATE execution_link_tickets SET expires_at='2000-01-01T00:00:00Z' WHERE binding_id IS NOT NULL")
        elif fault == 'connection':
            conn.execute("UPDATE execution_control_lanes SET connection_id='different-connection'")
        elif fault == 'generation':
            conn.execute('UPDATE execution_control_lanes SET connection_generation=connection_generation+1')
        elif fault == 'agent':
            scope = dict(scope, agent_id='different-agent')
        elif fault == 'scope':
            scope = dict(scope, credential_epoch=scope['credential_epoch'] + 1)
        args = dict(scope=scope, channel=channel, now=datetime.fromisoformat(deps.clock.now_iso().replace('Z','+00:00')))
        with pytest.raises(OktoNexusError):
            require_execution_lane(uow, **args)
        if fault is None:
            assert require_execution_lane(uow, **args, operator_containment=True) > args['now']
        else:
            with pytest.raises(OktoNexusError):
                require_execution_lane(uow, **args, operator_containment=True)
        assert conn.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
