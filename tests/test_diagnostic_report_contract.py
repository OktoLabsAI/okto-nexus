"""Shared synthetic format vectors; not a runtime/provider campaign."""
import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from okto_nexus.application.participant_diagnostics import ParticipantDiagnostics
from okto_nexus.application.project_diagnostics import ProjectDiagnostics
from okto_nexus.domain.diagnostic_report import (
    CONTRACT_SHA256, CHECK_IDS, CODES, POLICY_REASONS, STATUSES, TECHNICAL_STATES,
    project_report,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'diagnostics_v1'
VECTORS = json.loads((FIXTURES / 'vectors.json').read_text(encoding='utf-8'))
SCHEMA = json.loads((FIXTURES / 'schema.json').read_text(encoding='utf-8'))


def empty():
    return dict(profile='synthetic-profile', topology='remote_operator', checks=[],
                effects=dict(service_started=False, configuration_applied=False,
                             harness_started=False, work_submitted=False, grants_issued=False))


def test_common_artifact_digest_and_emitted_vocabulary():
    manifest = json.loads((FIXTURES / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected
    material = ''.join(f'{manifest["files"][name]}  {name}\n' for name in sorted(manifest['files']))
    assert hashlib.sha256(material.encode('utf-8')).hexdigest() == manifest['aggregate_sha256'] == CONTRACT_SHA256
    catalog = json.loads((FIXTURES / 'catalog.json').read_text(encoding='utf-8'))['components']['nexus']
    assert set(catalog['codes']) == CODES
    assert set(catalog['check_ids']) == CHECK_IDS


@pytest.mark.parametrize('vector', VECTORS['aggregation'], ids=lambda v: v['case'])
def test_shared_aggregation_vectors(vector):
    value = empty()
    identifiers = ['local_service', 'server_reachability', 'participant_authentication']
    value['checks'] = [dict(id=identifiers[i], status=status, code='CHECK_UNCONFIRMED')
                       for i, status in enumerate(vector['statuses'])]
    result = project_report(value, scope='managed_project')
    assert result['counts'] == vector['expected_counts']
    assert result['state'] == vector['expected_state']
    assert sum(result['counts'].values()) == len(result['checks'])
    jsonschema.validate(result, SCHEMA)


@pytest.mark.parametrize('vector', VECTORS['reports'], ids=lambda v: v['case'])
def test_shared_report_vectors_have_exact_counts_unique_subjects_and_valid_schema(vector):
    report = vector['report']
    assert vector['synthetic'] is True
    jsonschema.validate(report, SCHEMA)
    assert report['counts'] == {status: sum(c['status'] == status for c in report['checks']) for status in STATUSES}
    identities = {(c['id'], c['subject']['kind'], c['subject']['id']) for c in report['checks']}
    assert len(identities) == len(report['checks'])
    if report['component'] == 'nexus':
        source = empty()
        source.update(topology=report['topology'], checks=copy.deepcopy(report['checks']))
        assert project_report(source, scope=report['scope'],
                              explicit_checks=report['mode'] == 'explicit_checks') == report


@pytest.mark.parametrize('factory,scope', [
    (ProjectDiagnostics, 'managed_project'), (ParticipantDiagnostics, 'participant'),
])
def test_current_typed_defaults_are_preserved_without_observation(factory, scope, monkeypatch):
    import builtins
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail('Pure projection attempted an external effect')
    report = factory('synthetic-profile')
    source = report.result()
    original = copy.deepcopy(source)
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    result = project_report(source, scope=scope)
    assert source == original == report.result()
    assert result['counts'] == source['counts']
    assert result['effects'] == source['effects']
    assert 'credential_read' in result['effects'] if scope == 'participant' else 'credential_read' not in result['effects']
    for row, old in zip(result['checks'], source['checks']):
        assert all(row[key] == old[key] for key in ('id', 'status', 'code', 'reason', 'next_action'))
    jsonschema.validate(result, SCHEMA)


def test_untrusted_strings_and_nested_history_are_not_copied():
    value = empty()
    value['profile'] = 'nxs_SYNTHETIC_SENTINEL'
    value['checks'] = [dict(id='coordination_participation', status='UNKNOWN',
        code='ARBITRARY_SECRET_SENTINEL', reason='raw secret SENTINEL', next_action='echo SENTINEL',
        evidence=dict(source='local_receipt', qualification='identities_only', last_observed_status='PASS',
          smoke_id='smoke-one', request_ids=dict(message_create='one:message', handoff_create='one:handoff', unknown='SENTINEL'),
          observation=dict(body='SENTINEL', token='SENTINEL'), arbitrary='SENTINEL',
          server_id='nxs_SENTINEL', agent_id='agent-one', reference='NXS_SENTINEL'))]
    result = project_report(value, scope='participant')
    raw = json.dumps(result)
    assert 'SENTINEL' not in raw
    row = result['checks'][0]
    assert row['subject'] == dict(kind='profile', id='selected')
    assert row['code'] == 'CHECK_UNCONFIRMED' and row['status'] == 'UNKNOWN'
    assert row['evidence'] == dict(source='local_receipt', qualification='identities_only',
        last_observed_status='PASS', smoke_id='smoke-one', agent_id='agent-one',
        request_ids=dict(message_create='one:message', handoff_create='one:handoff'))
    assert result['state'] == 'incomplete'


def test_evidence_types_limits_and_effects_remain_separate_from_requested_mode():
    value = empty()
    value['effects'].update(credential_read=False, mcp_checked=False, raw='SENTINEL')
    value['checks'] = [dict(id='mcp_negotiation', status='UNKNOWN', code='MCP_NEGOTIATION_UNCONFIRMED',
        evidence=dict(tool_count=True, tools_called=True, compatible_surface='true',
          state='ARBITRARY', protocol_version='SENTINEL', operation_ids=['op'] * 120,
          technical_reasons=['SENTINEL', 'build_not_qualified'],
          policy_reasons=['AUTHORIZATION_REQUIRED', 'SENTINEL']))]
    result = project_report(value, scope='participant', explicit_checks=True)
    row = result['checks'][0]
    assert result['mode'] == 'explicit_checks' and not any(result['effects'].values())
    assert row['evidence'] == dict(operation_ids=['op'] * 100,
        technical_reasons=['build_not_qualified'], policy_reasons=['AUTHORIZATION_REQUIRED'])
    jsonschema.validate(result, SCHEMA)


@pytest.mark.parametrize('bad', [[], None, 1, True, 'unsupported'])
def test_invalid_scope_is_sanitized(bad):
    with pytest.raises(ValueError, match='^Invalid diagnostic projection context.$'):
        project_report(empty(), scope=bad)


@pytest.mark.parametrize('row', [
    dict(id=['SENTINEL'], status='PASS'), dict(id='SENTINEL', status='PASS'),
    dict(id='local_service', status='SENTINEL'), dict(id='local_service', status=True),
])
def test_malformed_check_is_refused_without_echo(row):
    value = empty()
    value['checks'] = [row]
    with pytest.raises(ValueError) as error:
        project_report(value, scope='managed_project')
    assert 'SENTINEL' not in str(error.value)


def test_duplicate_subject_check_is_refused():
    value = empty()
    value['checks'] = [dict(id='local_service', status='PASS', code='SERVICE_READY')] * 2
    with pytest.raises(ValueError, match='Duplicate diagnostic check'):
        project_report(value, scope='managed_project')


@pytest.mark.parametrize('state', sorted(TECHNICAL_STATES))
def test_canonical_availability_metadata_survives_without_implying_provider_readiness(state):
    value = empty()
    value['checks'] = [dict(id='runtime_eligibility', status='UNKNOWN', code='RUNTIME_UNCONFIRMED',
        evidence=dict(technical_state=state, policy_reasons=sorted(POLICY_REASONS),
                      technical_reasons=['no_build_observation']))]
    result = project_report(value, scope='managed_project')
    assert result['checks'][0]['evidence'] == value['checks'][0]['evidence']
    assert result['state'] == 'incomplete'
    assert result['checks'][0]['status'] == 'UNKNOWN'
    jsonschema.validate(result, SCHEMA)


def test_current_session_and_waiting_work_metadata_is_retained():
    value = empty()
    value['checks'] = [
        dict(id='managed_session', status='PASS', code='SESSION_CONTROL_AVAILABLE',
             evidence=dict(session_id='session-one', lifecycle_state='READY')),
        dict(id='work_result', status='UNKNOWN', code='WORK_NOT_COMPLETED',
             evidence=dict(state='needs_input', operation_ids=['operation-one'])),
    ]
    result = project_report(value, scope='managed_project')
    assert [row['evidence'] for row in result['checks']] == [row['evidence'] for row in value['checks']]
    assert result['state'] == 'incomplete' and result['counts']['PASS'] == 1
    jsonschema.validate(result, SCHEMA)


@pytest.mark.parametrize('state', ['stopped', 'failed'])
def test_service_failure_uses_the_shared_code_only_from_typed_state(state):
    value = empty()
    value['checks'] = [dict(id='local_service', status='FAIL', code='SERVICE_UNCONFIRMED',
                            evidence=dict(state=state))]
    before = copy.deepcopy(value)
    result = project_report(value, scope='managed_project')
    assert result['checks'][0]['code'] == 'SERVICE_NOT_READY'
    assert result['checks'][0]['status'] == 'FAIL'
    assert value == before
    jsonschema.validate(result, SCHEMA)


@pytest.mark.parametrize('state', ['credential_pending', 'credential_stored', 'file_pending', 'submission_unconfirmed'])
def test_current_checkpoint_states_are_retained_as_metadata(state):
    value = empty()
    value['checks'] = [dict(id='participant_profile', status='UNKNOWN', code='NOT_CHECKED',
                            evidence=dict(state=state))]
    result = project_report(value, scope='participant')
    assert result['checks'][0]['evidence']['state'] == state
    assert result['state'] == 'incomplete'
    jsonschema.validate(result, SCHEMA)
