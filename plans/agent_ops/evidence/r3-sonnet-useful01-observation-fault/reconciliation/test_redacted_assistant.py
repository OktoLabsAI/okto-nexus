import copy
import json
from pathlib import Path

import pytest
from nexus_connector_core.native.adapter_types import HarnessEvent
from nexus_connector_core.native.redaction import NativeSecretRedactor
from sonnet_usage import CampaignBudget, Ledger, Unknown, project

EVENTS = json.loads((Path(__file__).parent / 'events-projected.json').read_text())
OP = 'op_b9a7bc74da0788081adbe51fa62c6598'

def ledger():
    value = Ledger({k: EVENTS[0][k] for k in ('server_id','executor_id','session_id','stream_epoch')})
    value.reserve(OP)
    return value

def test_exact_closed_stream_reconciles_interrupted_not_success():
    value = ledger()
    for event in EVENTS:
        value.ingest(event)
    assert value.cursor == 98 and value.known == 36306
    assert value.active is None and value.terminal_coverage and not value.faults
    assert value.finished == [{'operation_id': OP, 'outcome': 'interrupted',
                               'tokens': 36306, 'input_tokens_including_cache': 35023}]
    assert len(value.reserved) == 1
    with pytest.raises(Unknown, match='REQUEST_REPLAY'):
        value.reserve(OP)

def test_installed_redactor_snapshot_is_not_an_identity_or_usage_source():
    value = ledger()
    for event in EVENTS[:18]:
        value.ingest(event)
    before = copy.deepcopy(value.messages)
    native = HarnessEvent('native','claude_code','output_delta','assistant','now',
        {'raw': {'message': {'id': 'msg_real', 'model': 'claude-sonnet-5-5',
                             'usage': {'input_tokens': 999999, 'cache_read_input_tokens': 0,
                                       'cache_creation_input_tokens': 0, 'output_tokens': 0},
                             'content': [{'type':'text','text':'do not publish'}]},
                 'parent_tool_use_id': None}}, output_snapshot=True)
    scrubbed = NativeSecretRedactor().scrub(native)
    event = {**EVENTS[18], 'payload': scrubbed.payload}
    projected = project(event)
    assert projected['payload']['message']['id'] == '[NATIVE_TEXT_REDACTED]'
    assert 'do not publish' not in json.dumps(projected)
    value.ingest(projected)
    assert value.known == 35031 and value.messages == before

@pytest.mark.parametrize('change', ['plain_id', 'partial_redaction', 'wrong_operation'])
def test_unrecognized_or_uncorrelated_snapshot_remains_fail_closed(change):
    value = ledger()
    for event in EVENTS[:18]:
        value.ingest(event)
    event = copy.deepcopy(EVENTS[18])
    if change == 'plain_id':
        event['payload']['message']['id'] = 'msg_other'
        event['payload']['message']['model'] = 'claude-sonnet-5-5'
    elif change == 'partial_redaction':
        event['payload']['message']['model'] = 'claude-sonnet-5-5'
    else:
        event['operation_id'] = 'another-operation'
    with pytest.raises(Unknown):
        value.ingest(event)
    assert value.faults and not value.terminal_coverage

def test_redacted_snapshot_does_not_replace_missing_stream_coverage():
    value = ledger()
    # Preserve sequence and kind so it is explicit that no stream was counted.
    for original in EVENTS:
        event = copy.deepcopy(original)
        if event['native_type'].startswith('stream_event:'):
            event['native_type'] = 'diagnostic:no_stream'
        if event['sequence'] == 19:
            with pytest.raises(Unknown, match='ASSISTANT_WITHOUT_STREAM'):
                value.ingest(event)
            break
        value.ingest(event)
    assert not value.terminal_coverage and value.active == OP
    assert value.known == 0  # The duplicate redacted snapshot supplies no usage proof.

def test_discrepant_terminal_still_refused():
    value = ledger()
    for event in EVENTS[:96]:
        value.ingest(event)
    event = copy.deepcopy(EVENTS[96])
    event['payload']['usage']['output_tokens'] += 1
    with pytest.raises(Unknown, match='FINAL_TURN_MISMATCH'):
        value.ingest(event)
    assert not value.terminal_coverage

def test_next_useful_headroom_does_not_promise_continuation():
    value = ledger()
    for event in EVENTS:
        value.ingest(event)
    budget = CampaignBudget()
    budget.sessions[tuple(value.scope.values())] = value
    assert budget.check_admission('useful')['reserved_next'] == 102046
    # Conservative scenario only, not an observed extra turn or allowance.
    value.known += 35023
    with pytest.raises(Unknown, match='NEXT_REQUEST_HEADROOM_INSUFFICIENT'):
        budget.check_admission('continuation')
