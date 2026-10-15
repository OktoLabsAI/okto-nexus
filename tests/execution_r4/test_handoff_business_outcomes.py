"""T32/T33: executed automatic work retains canonical verification and one outcome."""
from dataclasses import replace
import time

import pytest

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_canonical_result_publication import current_turn, emit
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_reserved_handoff_tools import capability, invoke


@pytest.mark.parametrize('audience', ['native', 'mcp'])
@pytest.mark.parametrize('verdict', ['plain', 'pass', 'fail'])
def test_executed_winner_keeps_single_canonical_outcome_and_rework_owner(runtime, audience, verdict):
    setup, binding, native = runtime
    deps, _, client, *_ = setup
    deps.config.feature_verification = True
    with deps.connection_factory.unit_of_work() as uow:
        # Conversation replies being enabled must not duplicate handoff outcomes.
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='conversation' WHERE endpoint_id=?", (binding['endpoint_id'],))
    _, hid, _ = prepare(runtime, **({'acceptance_criteria': ['Review the actual evidence']} if verdict != 'plain' else {}))
    enable_capacity(runtime)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    page = discovery.prepare_page(lease(runtime, hid), limit=4)
    assert len(page.attempt_ids) == 1
    assert client.portal.call(attempts.reserve, page.attempt_ids[0]).state == 'RESERVED'
    winner = attempts.claim(page.attempt_ids[0])
    client.portal.call(build_capacity_admission(deps).consume, winner.operation_id)
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    cap = capability(setup, binding, turn['session_id'], audience)
    emit(setup, native, turn, 'Actual native evidence for the governed work')
    # Wait for actual result processing; absence of a relay before the worker
    # runs would not prove that conversation publication was excluded.
    deadline = time.monotonic() + 15
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            result = uow.connection.execute('SELECT publication_state,publication_message_id FROM runtime_results').fetchone()
        if result and result[0] != 'PENDING_AUTHORIZATION':
            break
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert result[1] is None, 'Native final must not create a second conversational outcome'
    done, status = invoke(setup, cap, 'complete', hid, claim_epoch=1, result='Explicit reviewed result')
    assert status == 200 and done['status'] == ('COMPLETED' if verdict == 'plain' else 'VERIFYING'), done
    repeated, status = invoke(setup, cap, 'complete', hid, claim_epoch=1, result='Explicit reviewed result')
    assert (status == 200 and repeated == done) or (
        status == 403 and repeated['error']['code'] == 'INVALID_TRANSITION'), repeated
    if verdict != 'plain':
        feedback = {'feedback': 'Creator requests rework after actual execution'} if verdict == 'fail' else {}
        verified = call(runtime, 'handoff_verify', agent_id='caller', handoff_id=hid, claim_epoch=1,
                        verdict=verdict, **feedback)
        assert verified['ok'], verified
        again = call(runtime, 'handoff_verify', agent_id='caller', handoff_id=hid, claim_epoch=1,
                     verdict=verdict, **feedback)
        assert not again['ok'], again
    # Repeated authenticated completion and verifier calls must not create
    # another canonical event, inbox notification or native execution.
    epoch = 2 if verdict == 'fail' else 1
    after = discovery.prepare_page(replace(lease(runtime, hid), claim_generation=epoch), limit=4)
    assert not after.attempt_ids and after.settled
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == (
            'CLAIMED' if verdict == 'fail' else 'COMPLETED', 'subject', epoch)
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_results').fetchone()[0] == 1
        assert not uow.connection.execute('SELECT 1 FROM runtime_results WHERE publication_message_id IS NOT NULL').fetchone()
        events = dict(uow.connection.execute("SELECT type,COUNT(*) FROM events WHERE type IN "
            "('handoff.completed','handoff.verification_requested','handoff.verification_failed') GROUP BY type"))
        assert events.get('handoff.completed', 0) == int(verdict != 'fail')
        assert events.get('handoff.verification_requested', 0) == int(verdict != 'plain')
        assert events.get('handoff.verification_failed', 0) == int(verdict == 'fail')
        notifications = dict(uow.connection.execute("SELECT json_extract(body,'$.kind'),COUNT(*) FROM messages "
            "WHERE json_valid(body) AND json_extract(body,'$.handoff_id')=? GROUP BY json_extract(body,'$.kind')", (hid,)))
        # The creator receives completion directly as the verifier's own API
        # response; existing semantics deliberately omit self-notifications.
        assert notifications.get('handoff.completed', 0) == int(verdict == 'plain')
        assert notifications.get('handoff.verification_requested', 0) == int(verdict != 'plain')
        assert notifications.get('handoff.verification_failed', 0) == int(verdict == 'fail')
    assert native.opens == 1 and native.native.sent == [('send_turn', turn['operation_id'])]
