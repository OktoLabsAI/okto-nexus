"""Existing canonical synthetic admission/ingress feeds Home and Attention alike."""
# ruff: noqa: F811 -- reuse pytest fixture dependencies by their declared names
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_attention_native import decision_state, opening, isolated_native_inventory  # noqa: E402,F401
from okto_nexus.domain.runtime_context import RuntimeRequestContext  # noqa: E402
from okto_nexus.domain.attention import instant  # noqa: E402

OPERATOR = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)


@pytest.mark.parametrize('decision_state,display', [('input','awaiting_operator'),('agent_input','awaiting_agent')], indirect=['decision_state'])
def test_pending_classification_is_counted_before_page_and_preserves_recipient(decision_state, display):
    _, app, _ = decision_state
    service = app.state.home
    value = service.read(context=OPERATOR, section='work', filters={'state':display}, limit=1)
    assert value['total'] == 1 and value['items'][0]['display_state'] == display
    assert value['items'][0]['attention_refs']
    assert 'private-marker' not in json.dumps(value)
    assert service.read(context=OPERATOR)['summary']['running']['value'] == 0
    opposite = 'awaiting_agent' if display == 'awaiting_operator' else 'awaiting_operator'
    assert service.read(context=OPERATOR, section='work', filters={'state':opposite})['total'] == 0


def test_home_attention_cursor_is_the_existing_attention_cursor(decision_state):
    _, app, _ = decision_state
    service = app.state.home
    value = service.read(context=OPERATOR)
    canonical = app.state.attention.read(context=OPERATOR, filters={'category':'action_required'}, limit=3)
    assert value['attention']['revision'] == canonical['snapshot_revision']
    assert value['attention']['items'] == canonical['items']
    assert value['attention']['next_cursor'] == canonical['next_cursor']


@pytest.mark.parametrize('decision_state', ['input'], indirect=True)
def test_snooze_changes_needs_you_not_the_pending_work_state(decision_state):
    deps, app, _ = decision_state
    before = app.state.home.read(context=OPERATOR)
    occurrence = next(i for i in before['attention']['items'] if i['kind']=='native_question_pending')
    app.state.attention.snooze(context=OPERATOR, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=occurrence['seen_state']['revision'],
        until=(instant(deps.clock.now_iso())+timedelta(seconds=30)).isoformat())
    after = app.state.home.read(context=OPERATOR)
    assert after['summary']['needs_you']['value'] == before['summary']['needs_you']['value']-1
    assert next(i for i in after['work']['items'] if i['kind']=='direct_operation')['display_state']=='awaiting_operator'
