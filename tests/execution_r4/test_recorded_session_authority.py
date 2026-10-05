"""A persisted reply retains the sender's live session scope, never its secret."""
import copy
from dataclasses import replace
import json

import pytest

from okto_nexus.errors import OktoNexusError
from test_open_bootstrap import opening, begin
from test_session_capabilities import issue, service, apply_lease


def test_recorded_authority_rechecks_scope_actions_and_revocation(opening):
    issued = issue(opening, actions=['tools/call', 'runtime_input_respond']).json()
    begin(opening)
    leases, _, _, ack = apply_lease(opening)
    leases.applied(ack, channel=opening[5])
    factory = opening[0].connection_factory
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
    authority = service(opening)
    principal = authority.authenticate_transport(token=issued['capability'], audience='nexus-mcp-session')
    actions = ('tools/call', 'runtime_input_respond')
    with factory.unit_of_work() as uow:
        reference = authority.principal_reference(uow, principal=principal, actions=actions)
        assert set(reference) == {'capability_id', 'audience', 'scope'}
        assert issued['capability'] not in json.dumps(reference)
        assert principal.secret_hash not in json.dumps(reference)
        assert authority.authorize_recorded_principal(uow, reference=reference, actions=actions)['scope'] == dict(principal.scope)
        with pytest.raises(OktoNexusError):
            authority.principal_reference(uow, principal=replace(principal, capability_id='forged'), actions=actions)
        with pytest.raises(OktoNexusError):
            authority.authorize_recorded_principal(uow, reference=reference, actions=['message_create'])
        for changes in ({'capability_id': 'missing'}, {'audience': 'nexus-native-session'},
                        {'scope': dict(principal.scope) | {'workspace_id': 'other'}},
                        {'scope': dict(principal.scope) | {'agent_id': 'operator'}},
                        {'scope': dict(principal.scope) | {'session_owner_generation': 999}},
                        {'secret_hash': principal.secret_hash}):
            with pytest.raises(OktoNexusError):
                authority.authorize_recorded_principal(uow, reference=copy.deepcopy(reference) | changes, actions=actions)
        for sql in (
            "UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'",
            "UPDATE execution_session_capabilities SET valid_until_server='2000-01-01T00:00:00Z'",
            "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
            "UPDATE execution_sessions SET lifecycle_state='CLOSED'",
            "UPDATE execution_sessions SET owner_generation=owner_generation+1",
            "UPDATE execution_agent_revisions SET credential_epoch=credential_epoch+1 WHERE agent_id='subject'",
        ):
            uow.connection.execute('SAVEPOINT changed_authority')
            uow.connection.execute(sql)
            with pytest.raises(OktoNexusError):
                authority.authorize_recorded_principal(uow, reference=reference, actions=actions)
            uow.connection.execute('ROLLBACK TO changed_authority')
            uow.connection.execute('RELEASE changed_authority')
