"""Drain preserves existing authority checks, never issuing replacement grants."""
import pytest

from okto_nexus.errors import OktoNexusError
from test_open_bootstrap import begin
from test_session_capabilities import apply_lease, issue, use

pytest_plugins = ['test_session_capabilities']


@pytest.mark.parametrize('drift', [None, 'revoked_grant', 'expired_grant', 'expired_lease', 'inactive_actor'])
def test_existing_capability_and_lease_continue_only_under_current_authority(opening, drift):
    deps, _app, access, _context, _grant, channel, _resolution, _ = opening
    issued = issue(opening).json()
    begin(opening)
    leases, _request, granted, ack = apply_lease(opening)
    leases.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
        original = tuple(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
        cap_count = uow.connection.execute('SELECT COUNT(*) FROM execution_session_capabilities').fetchone()[0]
    deps.runtime_admission_fence.close()
    if drift:
        with deps.connection_factory.unit_of_work() as uow:
            if drift == 'revoked_grant':
                uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1',
                                       (deps.clock.now_iso(),))
            elif drift == 'expired_grant':
                uow.connection.execute("UPDATE runtime_execution_grants SET no_expiry=0,expires_at='2000-01-01T00:00:00Z'")
            elif drift == 'expired_lease':
                uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'")
            else:
                uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
        with pytest.raises(OktoNexusError):
            use(opening, issued)
        with pytest.raises(OktoNexusError):
            apply_lease(opening, serial=granted['lease_serial'], purpose='renew', request_id='drain-renew')
    else:
        use(opening, issued)
        renewed, _request, _grant, next_ack = apply_lease(opening, serial=granted['lease_serial'],
                                                       purpose='renew', request_id='drain-renew')
        renewed.applied(next_ack, channel=channel)
        use(opening, issued)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert tuple(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone()) == original
    # A current capability may authenticate; a new one is still new authority.
    denied = issue(opening, request_id='drain-must-not-issue')
    assert denied.status_code in {401, 403, 409}, denied.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_session_capabilities').fetchone()[0] == cap_count
    for action in ('open', 'send', 'steer'):
        with pytest.raises(OktoNexusError):
            access.require_admission(action)


def test_drain_cannot_issue_an_initial_lease_for_a_prepared_opening(opening):
    begin(opening)
    opening[0].runtime_admission_fence.close()
    with pytest.raises(OktoNexusError):
        apply_lease(opening)
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0


@pytest.mark.parametrize('drift', [None, 'expired_renewal', 'revoked_grant'])
def test_drain_reconciles_only_the_exact_live_renewal_already_issued(opening, drift):
    deps, _app, _access, _context, _grant, channel, _resolution, _ = opening
    begin(opening)
    leases, _request, first, ack = apply_lease(opening)
    leases.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
    leases, request, renewed, ack = apply_lease(opening, serial=first['lease_serial'],
        purpose='renew', request_id='already-issued')
    deps.runtime_admission_fence.close()
    # The peer may have installed the renewal before its ACK reached Server.
    # Expiring the previous lease must not erase this committed issuance.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z' WHERE lease_serial=1")
        if drift == 'expired_renewal':
            uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z' WHERE lease_serial=2")
        elif drift == 'revoked_grant':
            uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1',
                                   (deps.clock.now_iso(),))
        before = [tuple(row) for row in uow.connection.execute('SELECT * FROM execution_leases ORDER BY lease_serial')]
        source = tuple(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
    if drift:
        with pytest.raises(OktoNexusError):
            leases.issue(request, channel=channel)
        with pytest.raises(OktoNexusError):
            leases.applied(ack, channel=channel)
    else:
        assert leases.issue(request, channel=channel) == renewed
        # Recovery does not authorize a new issuance after the old lease expired.
        with pytest.raises(OktoNexusError):
            leases.issue(request | {'request_id': 'different-request'}, channel=channel)
        leases.applied(ack, channel=channel)
        leases.applied(ack, channel=channel)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = [tuple(row) for row in uow.connection.execute('SELECT * FROM execution_leases ORDER BY lease_serial')]
        assert len(after) == len(before) == 2
        assert tuple(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone()) == source
        if drift:
            assert after == before
        else:
            assert [row[0] for row in uow.connection.execute('SELECT status FROM execution_leases ORDER BY lease_serial')] == ['SUPERSEDED', 'ACTIVE']


def test_drain_does_not_install_a_previously_issued_initial_lease(opening):
    begin(opening)
    leases, request, _granted, ack = apply_lease(opening)
    opening[0].runtime_admission_fence.close()
    with pytest.raises(OktoNexusError):
        leases.issue(request, channel=opening[5])
    with pytest.raises(OktoNexusError):
        leases.applied(ack, channel=opening[5])
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM execution_leases').fetchone()[0] == 'ISSUED'
