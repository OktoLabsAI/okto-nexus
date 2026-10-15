"""An explicit operator opt-in is independent of ordinary runtime permission."""
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_runtime_policy_defaults import read, save
from okto_nexus.application.runtime_policy import guard, handoff_automation_guard


def snapshot(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return handoff_automation_guard(uow.connection, 'subject'), guard(uow.connection, 'subject')


def test_opt_in_inheritance_independent_of_conversation_and_execution(connected_local):
    setup, binding, native = connected_local
    # The approved, conversation-enabled connection must not enable automation.
    assert read(setup)['broadcast_handoff_auto_claim'] is False
    assert read(setup, 'subject')['broadcast_handoff_auto_claim'] is None
    assert not snapshot(setup)[0]['enabled']
    assert save(setup, broadcast_handoff_auto_claim=True).status_code == 200
    assert read(setup, 'subject')['effective']['broadcast_handoff_auto_claim'] is True
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    assert not snapshot(setup)[0]['enabled']
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=None).status_code == 200
    assert snapshot(setup)[0]['enabled']
    # Older editors omitting the new field preserve it.
    assert save(setup, inherit_global_mcps=True).status_code == 200
    assert read(setup)['broadcast_handoff_auto_claim'] is True
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT response_policy FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone()[0] == 'conversation'
    assert native.opens == 0


def test_opt_in_epoch_fences_old_attempt_without_revoking_live_runtime(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'before-auto-policy', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert save(setup, broadcast_handoff_auto_claim=True).status_code == 200
    first, runtime_guard = snapshot(setup)
    assert save(setup, broadcast_handoff_auto_claim=False).status_code == 200
    assert save(setup, broadcast_handoff_auto_claim=True).status_code == 200
    restored, same_runtime = snapshot(setup)
    assert restored['enabled'] and restored != first
    assert same_runtime == runtime_guard
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    explicit, _ = snapshot(setup)
    assert not explicit['inherited']
    assert save(setup, broadcast_handoff_auto_claim=False).status_code == 200
    assert snapshot(setup)[0] == explicit  # Unrelated defaults cannot revoke an override.
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=False).status_code == 200
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    assert snapshot(setup)[0] != explicit
    assert not native.native.stopped
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?', (opened['session_id'],)).fetchone()[:] == ('READY', 'ACTIVE')
        assert uow.connection.execute('SELECT count(*) FROM runtime_execution_grants WHERE revoked_at IS NOT NULL').fetchone()[0] == 0
    wait_receipt(setup, admit(setup, binding, 'after-auto-policy-close', 'runtime.close', session_id=opened['session_id']), stages=('SUCCEEDED',))


def test_only_operator_can_change_opt_in_and_values_are_strict(connected_local):
    setup = connected_local[0]
    for agent in (None, 'subject'):
        path = '/api/v1/runtime-policy' if agent is None else '/api/v1/agents/subject/runtime-policy'
        current = read(setup, agent)
        body = dict(expected_revision=current['revision'], runtime_enabled=current['runtime_enabled'],
                    session_policy=current['session_policy'], broadcast_handoff_auto_claim=True)
        assert setup[2].put(path, headers=setup[3]['subject'], json=body).status_code == 403
        for invalid in (1, 'true', [], {}):
            assert save(setup, agent=agent, broadcast_handoff_auto_claim=invalid).status_code == 422
        assert setup[2].put(path, headers=setup[3]['operator'], json=body).status_code == 200
        assert setup[2].put(path, headers=setup[3]['operator'], json=body).status_code == 409
    assert save(setup, broadcast_handoff_auto_claim=None).status_code == 422
