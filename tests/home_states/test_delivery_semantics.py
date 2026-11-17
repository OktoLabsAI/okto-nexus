"""Delivery meaning from explicit source facts; no runtime/provider execution."""
from copy import deepcopy

import pytest

from okto_nexus.domain.home_delivery_semantics import (
    delivery_reference,
    project,
    reported_semantics,
)


def facts(**changes):
    value = {'server_id': 'server', 'executor_id': 'executor', 'operation_id': 'operation',
        'workspace_id': 'workspace', 'stage': 'SUCCEEDED', 'terminal_sequence': 7}
    value.update(changes)
    return value


@pytest.mark.parametrize('stage,expected', [('SUCCEEDED', 'succeeded'), ('FAILED', 'failed'), ('CANCELLED', 'cancelled')])
def test_turn_outcome_does_not_invent_task_or_verification(stage, expected):
    value = project(facts(stage=stage))
    assert value['scope'] == 'turn' and value['execution_outcome'] == expected
    assert value['task_state'] == value['verification'] == 'not_applicable'
    assert not value['historical'] and value['verification_evidence_ref'] is None


@pytest.mark.parametrize('status,verification', [('OPEN', 'unknown'), ('CLAIMED', 'unknown'), ('VERIFYING', 'pending'), ('COMPLETED', 'unknown'), ('REJECTED', 'unknown')])
def test_task_status_is_independent_and_completed_never_proves_approved(status, verification):
    value = project(facts(handoff_id='handoff', claim_epoch=1, current_epoch=1,
        handoff_status=status, verification_required=True))
    assert value['task_state'] == status.lower()
    assert value['verification'] == verification
    assert value['execution_outcome'] == 'succeeded'


def verified_facts(verdict='pass'):
    ref = delivery_reference('workspace', 'handoff', 1, 'persisted delivery')
    proof = {'version': 1, 'kind': 'handoff_delivery', 'workspace_id': 'workspace', 'handoff_id': 'handoff', 'claim_epoch': 1,
        'delivery_revision': ref['delivery_revision'], 'event_id': 19, 'verified_by': 'reviewer', 'actor_agent_id': 'reviewer',
        'event_claim_epoch': 1, 'event_delivery_revision': ref['delivery_revision'], 'submission_event_id': 18,
        'verdict': verdict, 'event_type': 'handoff.completed' if verdict == 'pass' else 'handoff.verification_failed'}
    return facts(handoff_id='handoff', claim_epoch=1, current_epoch=1,
        handoff_status='COMPLETED', delivery_revision=ref['delivery_revision'], verification_proof=proof)


@pytest.mark.parametrize('verdict,expected', [('pass', 'approved'), ('fail', 'rejected')])
def test_exact_verification_proof_has_opaque_reference(verdict, expected):
    value = project(verified_facts(verdict))
    assert value['verification'] == expected
    assert value['verification_evidence_ref'].startswith('handoff-verification:19:')
    assert 'persisted delivery' not in str(value)


@pytest.mark.parametrize('field,value', [('claim_epoch', 2), ('workspace_id', 'foreign'),
    ('handoff_id', 'other'), ('delivery_revision', 'sha256:' + '0' * 64), ('event_type', 'handoff.created'),
    ('actor_agent_id', 'executor'), ('event_id', 0), ('version', 2), ('version', True),
    ('event_claim_epoch', 2), ('kind', 'external_report'), ('submission_event_id', 19), ('submission_event_id', 0)])
def test_proof_of_another_claim_revision_workspace_or_actor_is_not_inherited(field, value):
    source = verified_facts()
    source['verification_proof'][field] = value
    assert project(source)['verification'] == 'unknown'
    assert project(source)['verification_evidence_ref'] is None


def test_cleanup_and_content_do_not_overwrite_productive_outcome():
    value = project(facts(containment_state='REQUESTED', terminal_sequence=None))
    assert value['execution_outcome'] == 'succeeded'
    assert value['cleanup'] == 'pending' and value['content_state'] == 'pending'
    captured_empty = project(facts(containment_state='RELEASED', preview=None))
    assert captured_empty['cleanup'] == 'complete' and captured_empty['content_state'] == 'available'
    assert project(facts())['cleanup'] == 'unknown'


def test_historical_claim_is_explicit_and_never_inherits_current_verifying():
    value = project(facts(handoff_id='handoff', claim_epoch=1, current_epoch=2,
        handoff_status='VERIFYING', verification_required=True))
    assert value['historical'] and value['verification'] == 'unknown'


def test_external_report_has_no_native_success_and_revision_changes_without_mutation():
    report = {'source_revision': 'first', 'private': 'not projected'}
    before = deepcopy(report)
    first = reported_semantics(report)
    assert report == before and 'private' not in str(first)
    assert first['scope'] == 'external_report' and first['evidence'] == 'reported'
    assert first['execution_outcome'] == first['verification'] == 'unknown'
    assert first['semantic_revision'] != reported_semantics({'source_revision': 'second'})['semantic_revision']
