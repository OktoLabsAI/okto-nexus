"""QC F/H output contracts; synthetic canonical data, no provider or lifecycle."""
from copy import deepcopy
import json

import pytest

from okto_nexus.adapters.inbound.cli.quick_connect_outcome import annotate, display_public


def inputs():
    reference = dict(server_id='server', executor_id='executor', workspace_id='workspace', binding_id='binding',
        workspace_binding_id='mapping', agent_id='agent', endpoint_id='endpoint')
    public = dict(version=1, state='bound', connect_id='reviewer', canonical_ref=reference)
    root = '/approved project/with spaces'
    document = dict(selection=dict(client='claude', label='Minha aplicação & docs', project=root, agent='agent',
        workspace_id='workspace', binding_id='binding',
        public_connection=dict(version=1, connect_id='reviewer', reservation_ref='pcr_' + 'a' * 32,
            project_revision='sha256:' + 'b' * 64),
        quick_connect=dict(operation='created', project_name_source='explicit',
            name_discovery=dict(status='not_needed', reason='explicit_name'),
            cwd_resolution=dict(invocation_cwd=root, project_root=root, root_explicit=False, source='cwd'))))
    value = dict(state='configured', server_id='server', agent_id='agent', binding_id='binding', workspace_id='workspace',
        session_state='not_checked', work_state='not_submitted', public_connection=public,
        configuration=dict(connections=[dict(reference, adapter_id='claude_stream', execution_location='local')],
            folders=dict(workspace_root=root)))
    return value, document


def outcome(value, document, **kwargs):
    return annotate(value, document, profile='opaque-technical-profile', home='/safe home', **kwargs)


def test_legacy_value_is_unchanged_and_output_helper_defers_to_legacy_display(capsys):
    value = {'state': 'configured', 'legacy': {'untouched': True}}
    assert outcome(value, {'selection': {}}) is value
    assert display_public(value) is False
    assert capsys.readouterr().out == ''


def test_created_connection_reports_bound_full_reference_without_claiming_work_or_mutating_inputs(capsys):
    value, document = inputs()
    originals = deepcopy((value, document))
    result = outcome(value, document)
    quick = result['quick_connect']
    assert quick['version'] == 1 and quick['status'] == 'connected'
    assert quick['connect_id_status'] == 'bound' and quick['connect_id'] == 'reviewer'
    assert quick['operation'] == 'created'
    assert quick['canonical_reference'] == value['public_connection']['canonical_ref']
    assert result['session_state'] == 'not_checked' and result['work_state'] == 'not_submitted'
    assert 'proposed_connect_id' not in quick and 'harness_id' not in quick
    assert json.loads(json.dumps(result)) == result
    assert (value, document) == originals and capsys.readouterr().out == ''


def test_reuse_preserves_the_same_public_id_and_reference_and_names_the_reuse(capsys):
    value, document = inputs()
    result = outcome(value, document, operation='reused')
    assert result['quick_connect']['operation'] == 'reused'
    assert result['quick_connect']['connect_id'] == 'reviewer'
    assert display_public(result) is True
    output = capsys.readouterr().out
    assert 'reutilizada' in output and 'ID do Harness: reviewer' in output
    assert 'opaque-technical-profile' not in output


def test_partial_server_commit_keeps_bound_identity_and_shortcut_repair_explicit(capsys):
    value, document = inputs()
    value['state'] = 'configured_shortcut_pending'
    result = outcome(value, document)
    assert result['quick_connect']['status'] == 'configured_shortcut_pending'
    assert result['quick_connect']['connect_id_status'] == 'bound'
    assert result['quick_connect']['canonical_reference'] == value['public_connection']['canonical_ref']
    assert display_public(result) is True
    output = capsys.readouterr().out
    assert 'pending' in output and 'no new connection test' in output
    assert 'opaque-technical-profile' not in output


def test_plan_never_promotes_proposal_or_existing_observation_to_connected(capsys):
    value, document = inputs()
    result = outcome(value, document, plan=True)
    quick = result['quick_connect']
    assert quick['status'] == 'planned' and quick['connect_id_status'] == 'proposed'
    assert quick['proposed_connect_id'] == 'reviewer'
    assert 'connect_id' not in quick and 'canonical_reference' not in quick
    assert display_public(result) is False
    output = capsys.readouterr().out
    # False delegates the complete plan/review rendering to the caller.
    assert 'Conexão configurada' not in output and 'Conexão reutilizada' not in output


@pytest.mark.parametrize('state, expected', [('cancelled', 'cancelled'), ('conflict', 'conflict'),
    ('test_failed', 'failed'), ('outcome_unknown', 'unknown')])
def test_known_non_success_states_are_not_relabelled_as_pending(state, expected):
    value, document = inputs()
    value.pop('public_connection')
    value['state'] = state
    assert outcome(value, document)['quick_connect']['status'] == expected


@pytest.mark.parametrize('missing', ['server_id', 'executor_id', 'workspace_id', 'binding_id', 'workspace_binding_id', 'agent_id', 'endpoint_id'])
def test_incomplete_canonical_reference_never_satisfies_connected(missing, capsys):
    value, document = inputs()
    value['public_connection']['canonical_ref'].pop(missing)
    with pytest.raises((ValueError, TypeError, KeyError)):
        outcome(value, document)
    assert capsys.readouterr().out == ''


def test_public_reference_must_match_the_observed_connection_and_reviewed_id():
    for mutate in (lambda v: v['public_connection']['canonical_ref'].update(binding_id='foreign'),
        lambda v: v['public_connection'].update(connect_id='another')):
        value, document = inputs()
        mutate(value)
        with pytest.raises(ValueError):
            outcome(value, document)


def test_resume_argv_uses_public_id_and_preserves_metacharacters_as_unexecuted_arguments(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Annotating output must not execute or rediscover anything')
    value, document = inputs()
    label = "My project & $(not-executed) 'quoted'"
    document['selection']['label'] = label
    with monkeypatch.context() as scoped:
        scoped.setattr('subprocess.run', forbidden)
        scoped.setattr('subprocess.Popen', forbidden)
        scoped.setattr('builtins.open', forbidden)
        result = outcome(value, document)
    argv = result['quick_connect']['resume_argv']
    assert isinstance(argv, list) and argv[:2] == ['okto-nexus', 'connect']
    assert argv[argv.index('--id') + 1] == 'reviewer'
    assert label in argv and 'claude' in argv
    assert json.loads(json.dumps(argv)) == argv


def test_positive_basic_output_identifies_project_origin_and_approved_root_before_chat(capsys):
    value, document = inputs()
    assert display_public(outcome(value, document)) is True
    output = capsys.readouterr().out
    assert 'ID do Harness: reviewer' in output
    assert document['selection']['project'] in output
    assert 'explicit' in output
    assert 'opaque-technical-profile' not in output and 'Project assistant' not in output
    assert 'not checked' in output and 'No project work submitted' in output


def test_unsafe_discovery_provenance_is_rejected_without_leaking_origin_or_credentials(capsys):
    value, document = inputs()
    document['selection']['quick_connect']['name_discovery']['reason'] = 'https://user:private-token@example.invalid/repo'
    with pytest.raises(ValueError) as failure:
        outcome(value, document)
    assert 'private-token' not in str(failure.value)
    assert capsys.readouterr().out == ''
