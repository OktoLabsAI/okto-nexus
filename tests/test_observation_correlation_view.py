"""Synthetic pure DTO comparisons; no live process, provider or OS qualification."""
import builtins
from copy import deepcopy
import json
import socket
import sqlite3
import subprocess

import pytest

from okto_nexus.application.observation_correlation_view import attach_canonical


NOW = '2026-11-07T12:00:00.000000Z'


@pytest.fixture
def records():
    view = dict(observed_instance_id='observation-one', source_id='source-one', source_revision=2,
        generation=3, agent_id='alice', workspace_id='workspace-one', freshness='current',
        activity_state='busy', last_report=dict(sequence=7, state='busy', evidence='inferred'),
        observational_only=True, canonical_session_ref=None)
    selection = dict(source_id='source-one', source_revision=2, observed_instance_id='observation-one',
        generation=3, server_id='server-one', executor_id='executor-one', session_id='session-one',
        open_operation_id='opening-one', session_owner_generation=4, stream_epoch='stream-one',
        binding_id='binding-one', workspace_binding_id='workspace-binding-one', expected_correlation_revision=0)
    scope = {key: selection[key] for key in (
        'server_id', 'executor_id', 'session_id', 'binding_id', 'workspace_binding_id', 'session_owner_generation')}
    scope.update(agent_id='alice', workspace_id='workspace-one', binding_revision=5)
    native = {key: selection[key] for key in (
        'server_id', 'executor_id', 'session_id', 'open_operation_id', 'binding_id', 'workspace_binding_id', 'stream_epoch')}
    native.update(owner_generation=4, opening_action='runtime.open', opening_session_id='session-one',
        opening_binding_id='binding-one', opening_workspace_binding_id='workspace-binding-one',
        binding_workspace_binding_id='workspace-binding-one', realization_workspace_binding_id='workspace-binding-one',
        subject_agent_id='alice', endpoint_agent_id='alice', realization_agent_id='alice',
        workspace_id='workspace-one', opening_workspace_id='workspace-one', endpoint_workspace_id='workspace-one',
        bound_workspace_id='workspace-one', expected_revisions_json=json.dumps(scope), binding_revision=5,
        kind='embedded', revoked_at=None, protocol='nxl-r4', endpoint_enabled=1, activation_state='approved',
        health='healthy', realization_revision=6, current_realization_revision=6, realization_status='READY',
        workspace_status='READY', control_state='CONTROL_READY', lifecycle_state='READY')
    correlation = dict(observed_instance_id='observation-one', agent_id='alice', workspace_id='workspace-one',
        revision=1, state='selected', selection=selection, verified_at=NOW,
        provenance=dict(external_binding_provenance='operator_attested_external_binding',
                        native_birth_provenance='machine_checked_native_birth'),
        proof=dict(pid=123, image_path='PRIVATE_PROCESS_PATH', token='PRIVATE_TOKEN'))
    receipt = dict(status='verified', operation_id='turn-one', action='turn.submit', stage='SUCCEEDED',
        receipt_revision=3, received_at=NOW, provenance='core_committed')
    return view, dict(correlation=correlation, native=native, last_received_receipt=receipt)


def test_matching_correlation_adds_minimal_canonical_facts_without_reinterpreting_external_activity(records):
    view, facts = records
    before = deepcopy(records)
    value = attach_canonical(view, facts)
    assert value is not view
    assert value['canonical_session_ref'] == dict(server_id='server-one', executor_id='executor-one',
        session_id='session-one', open_operation_id='opening-one', session_owner_generation=4, stream_epoch='stream-one')
    assert value['canonical_observation'] == dict(correlation_revision=1, verified_at=NOW,
        provenance=facts['correlation']['provenance'], session_lifecycle_state='READY',
        last_received_receipt=facts['last_received_receipt'], precedence='canonical_core_facts')
    assert {key: value[key] for key in view if not key.startswith('canonical_')} == {
        key: view[key] for key in view if not key.startswith('canonical_')}
    assert records == before
    assert value['activity_state'] == 'busy'  # SUCCEEDED is a receipt, not current idle/capacity.
    assert not {'idle', 'alive', 'available', 'capacity', 'effective_activity_state'} & value.keys()


def test_new_metadata_is_detached_and_private_facts_are_never_projected(records):
    view, facts = records
    facts['native'].update(canonical_frame='PRIVATE_FRAME', cwd='PRIVATE_CWD', native_id='PRIVATE_NATIVE')
    facts['last_received_receipt'].update(native_id='PRIVATE_NATIVE', error='PRIVATE_ERROR', canonical_frame='PRIVATE_FRAME')
    value = attach_canonical(view, facts)
    assert 'PRIVATE_' not in json.dumps(value)
    assert not {'proof', 'pid', 'host_id', 'image_path', 'token', 'binding_hash'} & value['canonical_observation'].keys()
    value['canonical_session_ref']['session_id'] = 'changed'
    value['canonical_observation']['provenance']['native_birth_provenance'] = 'changed'
    value['canonical_observation']['last_received_receipt']['stage'] = 'changed'
    assert facts['correlation']['selection']['session_id'] == 'session-one'
    assert facts['correlation']['provenance']['native_birth_provenance'] == 'machine_checked_native_birth'
    assert facts['last_received_receipt']['stage'] == 'SUCCEEDED'


@pytest.mark.parametrize('change', ['absent', 'cleared', 'revoked', 'source', 'source_revision', 'generation',
    'instance', 'agent', 'workspace', 'unavailable', 'native_absent', 'owner', 'stream', 'namespace', 'binding',
    'realization', 'endpoint_revoked', 'opening_scope'])
def test_stale_scope_or_replacement_clears_previous_enrichment_without_remapping(records, change):
    view, facts = records
    view = attach_canonical(view, facts)
    if change == 'absent':
        facts = None
    elif change in ('cleared', 'revoked'):
        facts['correlation']['state'] = change
    elif change in ('source', 'source_revision', 'generation', 'instance', 'agent', 'workspace'):
        key = dict(source='source_id', instance='observed_instance_id', agent='agent_id', workspace='workspace_id').get(change, change)
        view[key] = view[key] + 1 if type(view[key]) is int else 'different'
    elif change == 'unavailable':
        view['freshness'] = 'unavailable'
    elif change == 'native_absent':
        facts['native'] = None
    elif change == 'endpoint_revoked':
        facts['native']['activation_state'] = 'revoked'
    elif change == 'opening_scope':
        facts['native']['expected_revisions_json'] = '{}'
    else:
        key = dict(owner='owner_generation', stream='stream_epoch', namespace='executor_id',
                   binding='binding_id', realization='current_realization_revision')[change]
        facts['native'][key] = facts['native'][key] + 1 if type(facts['native'][key]) is int else 'different'
    value = attach_canonical(view, facts)
    assert value['canonical_session_ref'] is value['canonical_observation'] is None
    assert value['last_report'] == view['last_report']


@pytest.mark.parametrize('state', ['OPEN_PENDING', 'READY', 'CLOSED', 'FAILED'])
def test_known_lifecycle_is_historical_and_does_not_require_current_process_liveness(records, state):
    view, facts = records
    view.update(freshness='stale', activity_state='unknown')
    facts['native'].update(lifecycle_state=state, control_state='RECOVERING')
    value = attach_canonical(view, facts)
    assert value['canonical_observation']['session_lifecycle_state'] == state
    assert value['freshness'] == 'stale' and value['activity_state'] == 'unknown'


def test_future_lifecycle_does_not_leak_free_text_or_change_external_activity(records):
    view, facts = records
    facts['native']['lifecycle_state'] = 'PRIVATE_NEW_NATIVE_STATE'
    value = attach_canonical(view, facts)
    assert value['canonical_observation']['session_lifecycle_state'] == 'UNKNOWN'
    assert 'PRIVATE_' not in json.dumps(value)


@pytest.mark.parametrize('receipt', [None, dict(status='unknown', reason='receipt_provenance_unavailable')])
def test_absent_and_unverifiable_latest_receipts_remain_distinct(records, receipt):
    view, facts = records
    facts['last_received_receipt'] = receipt
    value = attach_canonical(view, facts)
    assert value['canonical_observation']['last_received_receipt'] == receipt


def test_unknown_receipt_cannot_copy_free_reason_or_promote_old_success(records):
    view, facts = records
    facts['last_received_receipt'] = dict(status='unknown', reason='PRIVATE_REASON', stage='SUCCEEDED')
    assert attach_canonical(view, facts)['canonical_observation']['last_received_receipt'] == dict(
        status='unknown', reason='receipt_provenance_unavailable')


@pytest.mark.parametrize('change', ['provenance', 'revision_bool', 'revision_stale', 'timestamp', 'scope_json'])
def test_malformed_private_facts_cannot_create_a_current_reference(records, change):
    view, facts = records
    if change == 'provenance':
        facts['correlation']['provenance']['external_binding_provenance'] = 'machine_checked'
    elif change.startswith('revision'):
        facts['correlation']['revision'] = True if change == 'revision_bool' else 2
    elif change == 'timestamp':
        facts['correlation']['verified_at'] = 'PRIVATE_INVALID_TIME'
    else:
        facts['native']['expected_revisions_json'] = 'PRIVATE_INVALID_JSON'
    value = attach_canonical(view, facts)
    assert value['canonical_session_ref'] is value['canonical_observation'] is None


@pytest.mark.parametrize('key,value', [('provenance', 'operator_attested'), ('receipt_revision', True),
    ('received_at', 'not-a-date'), ('stage', {'raw': 'PRIVATE_FRAME'})])
def test_malformed_verified_receipt_is_unknown_without_changing_valid_session_reference(records, key, value):
    view, facts = records
    facts['last_received_receipt'][key] = value
    result = attach_canonical(view, facts)
    assert result['canonical_session_ref'] is not None
    assert result['canonical_observation']['last_received_receipt'] == dict(
        status='unknown', reason='receipt_provenance_unavailable')


def test_projection_does_not_open_files_database_network_or_processes(records, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Pure view projection attempted I/O')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', forbidden)
        patch.setattr(sqlite3, 'connect', forbidden)
        patch.setattr(socket, 'socket', forbidden)
        patch.setattr(subprocess, 'Popen', forbidden)
        value = attach_canonical(*records)
    assert value['canonical_observation']['last_received_receipt']['stage'] == 'SUCCEEDED'


@pytest.mark.parametrize('field', ['binding_revision', 'session_owner_generation'])
@pytest.mark.parametrize('value', [True, 1.0])
def test_equal_numeric_json_of_another_type_cannot_establish_native_scope(records, field, value):
    from okto_nexus.application.observation_correlation_service import canonical_matches
    view, facts = records
    native, selection = facts['native'], facts['correlation']['selection']
    native.update(binding_revision=1, owner_generation=1)
    selection['session_owner_generation'] = 1
    scope = json.loads(native['expected_revisions_json'])
    scope.update(binding_revision=1, session_owner_generation=1)
    native['expected_revisions_json'] = json.dumps(scope)
    assert canonical_matches(native, selection, agent_id=view['agent_id'], workspace_id=view['workspace_id'], live=True)
    assert attach_canonical(view, facts)['canonical_session_ref'] is not None
    scope[field] = value
    native['expected_revisions_json'] = json.dumps(scope)
    assert not canonical_matches(native, selection, agent_id=view['agent_id'], workspace_id=view['workspace_id'], live=True)
    assert attach_canonical(view, facts)['canonical_session_ref'] is None


@pytest.mark.parametrize('raw', ['{', '[]', 'null', None])
def test_invalid_persisted_scope_is_a_refusal_before_host_proof(records, raw):
    from okto_nexus.application.observation_correlation_service import canonical_matches
    view, facts = records
    facts['native']['expected_revisions_json'] = raw
    assert not canonical_matches(facts['native'], facts['correlation']['selection'],
        agent_id=view['agent_id'], workspace_id=view['workspace_id'], live=True)
