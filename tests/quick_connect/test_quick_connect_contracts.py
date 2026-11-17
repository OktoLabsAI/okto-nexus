"""Pure QC-002 contracts; these tests do not qualify setup or a real harness."""
from dataclasses import FrozenInstanceError, fields, replace
import json

import pytest

from okto_nexus.domain.quick_connect import (
    CanonicalConnectionReference, ConnectionIntent, CwdResolution, NameDiscovery,
    ProjectNameChoice, QuickConnectOutcome, normalize_connect_id,
)


def reference(**changes):
    value = dict(server_id='Server:A', executor_id='Host/B', workspace_id='Project:C',
        binding_id='Binding:D', workspace_binding_id='Mapping:E', agent_id='Agent:F', endpoint_id='Endpoint:G')
    return CanonicalConnectionReference(**(value | changes))


def connected(**changes):
    value = dict(status='connected', connect_id='Reviewer', connect_id_status='bound', operation='created',
        harness='claude', project_name='Minha aplicação', canonical_reference=reference())
    return QuickConnectOutcome(**(value | changes))


@pytest.mark.parametrize('value, expected', [('Reviewer', 'reviewer'), ('A', 'a'), ('codex-2', 'codex-2'),
    ('CodeX_3', 'codex_3'), ('Z' + '9' * 63, 'z' + '9' * 63)])
def test_public_id_normalization_has_exact_ascii_boundaries(value, expected):
    assert normalize_connect_id(value) == expected


@pytest.mark.parametrize('value', ['', 'a' * 65, '2codex', '_codex', '-codex', 'codex/a', r'codex\a',
    'codex..', 'codex a', ' codex', 'codex ', 'codex\n', 'codex\x1b[0m', 'códex', 'ｃodex',
    'codex\u200b', None, True, 1, ['codex']])
def test_invalid_public_id_is_refused_without_echoing_input(value):
    with pytest.raises(ValueError) as failure:
        normalize_connect_id(value)
    assert 'Harness ID' in str(failure.value)
    if isinstance(value, str) and value:
        assert value not in str(failure.value)


def test_intent_preserves_requested_harness_and_separate_physical_context():
    intent = ConnectionIntent('CoDxE', 'Logical project', 'Reviewer', '/mono/apps/api', '/elsewhere/root', True)
    assert intent.requested_harness == 'CoDxE'  # Resolver, not this DTO, chooses a public harness.
    assert intent.project_name == 'Logical project'
    assert intent.invocation_cwd == '/mono/apps/api' and intent.project_root == '/elsewhere/root'
    assert intent.connect_id == 'reviewer' and intent.root_explicit is True and intent.new_connection is False
    assert [field.name for field in fields(intent)] == ['requested_harness', 'project_name', 'connect_id',
        'invocation_cwd', 'project_root', 'root_explicit', 'new_connection']
    with pytest.raises(FrozenInstanceError):
        intent.project_root = '/mono'


@pytest.mark.parametrize('patch', [{'root_explicit': 1}, {'new_connection': 'yes'}, {'invocation_cwd': ''},
    {'project_root': '\x00'}, {'project_name': 'bad\nname'}])
def test_intent_flags_and_required_context_are_not_coerced(patch):
    value = dict(requested_harness=None, project_name=None, connect_id=None, invocation_cwd='/cwd',
        project_root='/cwd', root_explicit=False)
    with pytest.raises(ValueError):
        ConnectionIntent(**(value | patch))


def test_name_choice_is_only_provenance_and_uses_safe_reason_constants():
    choice = ProjectNameChoice('monorepo', 'git_origin', 'suggested', 'git_origin')
    assert choice.name == 'monorepo' and choice.status == 'suggested'
    with pytest.raises(FrozenInstanceError):
        choice.name = 'another'
    for constructor in (lambda: NameDiscovery('fallback', 'https://user:secret@example/repo'),
        lambda: ProjectNameChoice('repo', 'git_origin', 'suggested', 'private-input'),
        lambda: NameDiscovery('anything', 'git_unavailable'),
        lambda: ProjectNameChoice('repo', 'branch', 'suggested', 'git_origin')):
        with pytest.raises(ValueError) as failure:
            constructor()
        assert 'secret' not in str(failure.value)


def test_connected_requires_full_bound_reference_but_does_not_rename_canonical_ids():
    result = connected()
    assert result.connect_id == 'reviewer'
    assert result.canonical_reference.binding_id == 'Binding:D'
    assert result.canonical_reference.agent_id == 'Agent:F'
    for patch in ({'connect_id_status': 'reserved'}, {'connect_id': None}, {'canonical_reference': None},
        {'canonical_reference': {'binding_id': 'Binding:D'}}, {'operation': None}, {'harness': None}, {'project_name': None}):
        with pytest.raises(ValueError):
            connected(**patch)
    for field in fields(CanonicalConnectionReference):
        with pytest.raises(ValueError):
            reference(**{field.name: ''})


@pytest.mark.parametrize('status', ['planned', 'selection_required', 'conflict', 'pending', 'cancelled', 'unknown', 'failed'])
def test_unbound_ids_have_a_separate_proposed_field(status):
    result = QuickConnectOutcome(status=status, proposed_connect_id='CodeX-2', connect_id_status='reserved' if status == 'pending' else 'proposed')
    wire = result.to_dict()
    assert wire['proposed_connect_id'] == 'codex-2'
    assert 'connect_id' not in wire and 'canonical_reference' not in wire
    assert wire['status'] != 'connected'
    with pytest.raises(ValueError):
        QuickConnectOutcome(status=status, connect_id='codex-2', connect_id_status='reserved')


def test_plan_cannot_claim_bound_or_hide_proposed_id_in_final_field():
    with pytest.raises(ValueError):
        connected(status='planned')
    with pytest.raises(ValueError):
        QuickConnectOutcome(status='planned', connect_id_status='proposed')
    with pytest.raises(ValueError):
        connected(proposed_connect_id='another')


def test_committed_shortcut_pending_can_preserve_bound_reference_without_claiming_connected():
    result = connected(status='configured_shortcut_pending')
    assert result.to_dict()['connect_id_status'] == 'bound'
    assert result.status != 'connected'


def test_wire_outcome_is_fresh_json_with_structured_cwd_and_no_parallel_public_id():
    result = connected(project_root='/mono/apps/api', project_name_source='git_origin',
        name_discovery=NameDiscovery('discovered', 'git_origin'),
        cwd_resolution=CwdResolution('/mono/apps/api', '/mono/apps/api', False, 'cwd'),
        resume_argv=('okto-nexus', 'connect', 'claude', 'Minha aplicação', '--id', 'reviewer'))
    wire = result.to_dict()
    assert json.loads(json.dumps(wire, ensure_ascii=False)) == wire
    assert wire['cwd_resolution'] == dict(invocation_cwd='/mono/apps/api', project_root='/mono/apps/api', root_explicit=False, source='cwd')
    assert wire['name_discovery'] == dict(status='discovered', reason='git_origin')
    assert 'harness_id' not in wire and 'profile' not in wire and 'proposed_connect_id' not in wire
    wire['canonical_reference']['agent_id'] = 'changed'
    wire['resume_argv'].append('not-executed')
    assert result.canonical_reference.agent_id == 'Agent:F'
    assert result.resume_argv[-1] == 'reviewer'
    with pytest.raises(ValueError):
        replace(result, cwd_resolution=CwdResolution('/mono/apps/api', '/mono', False, 'cwd'))


def test_versions_and_nested_objects_are_strict_and_deeply_immutable():
    for patch in ({'version': True}, {'version': 2}, {'status': 'configured'}, {'name_discovery': {}},
        {'cwd_resolution': '/cwd'}, {'resume_argv': ['okto-nexus']}, {'resume_argv': ('bad\x00arg',)}):
        with pytest.raises(ValueError):
            connected(**patch)
    with pytest.raises(FrozenInstanceError):
        connected().canonical_reference.agent_id = 'another'


def test_remote_context_can_omit_host_path_without_fabricating_local_root():
    result = connected(execution_location='remote', cwd_resolution=CwdResolution('/operator/cwd', None, False, 'remote'))
    assert result.to_dict()['cwd_resolution']['project_root'] is None
    assert 'project_root' not in result.to_dict()


def test_construction_and_serialization_need_no_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Pure contracts must not discover, read or execute')
    with monkeypatch.context() as scoped:
        scoped.setattr('builtins.open', forbidden)
        scoped.setattr('os.getcwd', forbidden)
        scoped.setattr('pathlib.Path.resolve', forbidden)
        scoped.setattr('subprocess.run', forbidden)
        scoped.setattr('subprocess.Popen', forbidden)
        intent = ConnectionIntent('codex', None, None, '/cwd', '/cwd', False)
        result = connected()
        wire = result.to_dict()
    assert intent.project_root == '/cwd' and wire['status'] == 'connected'
