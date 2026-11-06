"""Canonical local archive closes native attention without deciding the runtime."""
import pytest

import test_attention_native as native

from okto_nexus.application.attention_native import project
from okto_nexus.domain.attention import stamp
from okto_nexus.errors import OktoNexusError

decision_state = native.decision_state
opening = native.opening
isolated_native_inventory = native.isolated_native_inventory


@pytest.mark.parametrize('decision_state,kind,action', [
    (None, 'native_permission_pending', 'decide_native'),
    ('input', 'native_question_pending', 'respond_native'),
], indirect=['decision_state'])
def test_canonical_archive_closes_native_attention_with_stable_history(decision_state, kind, action):
    deps, _, _ = decision_state
    facts, policy, now = native.snapshot(deps)
    before, = project(facts[0], now, policy)
    assert before['kind'] == kind and action in before['allowed_actions']
    approval_id = before['source_id']

    archived = deps.approvals.archive(approval_id=approval_id, archived_by='operator')
    assert archived['status'] == 'archived'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        approval = uow.connection.execute('SELECT * FROM approvals WHERE approval_id=?', (approval_id,)).fetchone()
        request = uow.connection.execute('SELECT * FROM execution_native_requests WHERE canonical_request_id=?',
            (approval_id,)).fetchone()
        assert approval['status'] == 'pending' and request['state'] == 'PENDING'
        archived_at = approval['archived_at']
    with pytest.raises(OktoNexusError, match='archived'):
        deps.approvals.decide(approval_id=approval_id, decision='approve', decided_by='operator')

    facts, policy, now = native.snapshot(deps)
    after, = project(facts[0], now, policy)
    assert after['attention_id'] == before['attention_id']
    assert after['kind'] == kind and after['source_revision'] != before['source_revision']
    assert after['resolution'] == 'resolved' and after['active'] is False
    assert after['category'] == 'watch' and after['allowed_actions'] == ['inspect_approval']
    assert after['first_detected_at'] == before['first_detected_at']
    assert after['last_changed_at'] == stamp(archived_at) and after['next_change_at'] is None
    # Archived history does not require rebuilding a current live runtime authority.
    assert facts[0]['runtime'] is None
    assert deps.approvals.archive(approval_id=approval_id, archived_by='operator') == archived
    facts, policy, now = native.snapshot(deps)
    assert project(facts[0], now, policy) == [after]
