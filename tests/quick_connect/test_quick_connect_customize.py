"""QC021 restart proposal contracts; no Server, Git, provider or lifecycle effects."""
from copy import deepcopy

import pytest

from okto_nexus.adapters.inbound.cli.connect_arguments import parse_connect_args
from okto_nexus.adapters.inbound.cli.quick_connect_customize import customize, ReviewRestart
from okto_nexus.adapters.inbound.cli.quick_connect_outcome import public_wire
from okto_nexus.application.terminal_connection import ConnectionError


def reviewed(tmp_path, *extra, association=False, named=False):
    argv = ['codex', *(['Explicit project'] if named else []), '--profile', 'old-profile',
        '--approve', 'old-approved-hash', '--project', str(tmp_path), '--candidate-ref', 'candidate-old',
        '--no-chat', '--no-start-at-login', *extra]
    args, _ = parse_connect_args(argv)
    document = dict(kind='public_id_association' if association else 'managed_setup', state='review',
        review_revision='old-approved-hash', request=dict(setup_intent_id='old-intent'), selection=dict(
            client='codex', project=str(tmp_path), label='Explicit project' if named else 'Saved Git name', workspace_id='canonical-workspace',
            agent='existing-agent', binding_id='existing-binding',
            public_connection=dict(connect_id='codex-old', reservation_ref='old-reservation'),
            quick_connect=dict(project_name_source='git_origin', cwd_resolution=dict(
                invocation_cwd='original-invocation', project_root=str(tmp_path), root_explicit=True,
                source='explicit_project'))))
    return args, document


def change(args, document, *answers, service_args=None):
    responses = iter(answers)
    return customize(args, service_args or [], document, invocation_cwd='original-invocation',
        read=lambda _: next(responses), write=lambda _: None)


@pytest.mark.parametrize('choice,value', [('1', 'NEW-id'), ('2', 'New project'), ('3', 'CLAUDE'), ('4', None)])
def test_each_change_is_a_fresh_unapproved_profile_and_preserves_review(tmp_path, choice, value):
    folder = tmp_path / 'other execution'
    folder.mkdir()
    args, document = reviewed(tmp_path)
    before_args, before_document = deepcopy(vars(args)), deepcopy(document)
    service = ['--home', str(tmp_path / 'home'), '--port', '51076']
    result = change(args, document, choice, value or str(folder), service_args=service)
    assert isinstance(result, ReviewRestart)
    updated, retained_service = parse_connect_args(result.argv)
    assert retained_service == service
    assert result.invocation_cwd == 'original-invocation'
    assert updated.profile.startswith('connection-') and updated.profile != args.profile
    assert updated.approve is None and updated.new_connection
    assert updated.no_chat and updated.start_at_login is False
    assert '--approve' not in result.argv and 'old-intent' not in result.argv and 'old-reservation' not in result.argv
    assert vars(args) == before_args and document == before_document
    if choice == '1':
        assert updated.connect_id == 'new-id' and updated.workspace_id == 'canonical-workspace'
        assert result.frozen_name == dict(name='Saved Git name', source='git_origin', status='saved',
            reason='saved_selection', cwd_resolution=document['selection']['quick_connect']['cwd_resolution'],
            workspace_id='canonical-workspace')
    elif choice == '2':
        assert updated.project_name == 'New project' and updated.workspace_id is None
        assert result.frozen_name is None
    elif choice == '3':
        assert updated.client == 'claude' and updated.connect_id is None and updated.candidate_ref is None
        assert updated.workspace_id == 'canonical-workspace'
        assert result.frozen_name['name'] == 'Saved Git name'
    else:
        assert updated.project == folder.resolve() and updated.workspace_id is None
        assert result.frozen_name is None


def test_repeated_customization_does_not_reuse_generated_profile(tmp_path):
    args, document = reviewed(tmp_path)
    first, second = [change(args, document, '1', 'next') for _ in range(2)]
    assert parse_connect_args(first.argv)[0].profile != parse_connect_args(second.argv)[0].profile


def test_explicit_name_is_retained_instead_of_git_rediscovery(tmp_path, monkeypatch):
    args, document = reviewed(tmp_path, named=True)
    import subprocess
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('customization must not rediscover Git'))
    result = change(args, document, '1', 'next')
    assert parse_connect_args(result.argv)[0].project_name == 'Explicit project'
    assert result.frozen_name['name'] == 'Explicit project'
    assert result.frozen_name['cwd_resolution'] == document['selection']['quick_connect']['cwd_resolution']


@pytest.mark.parametrize('choice,value', [('1', 'replacement'), ('3', 'claude')])
def test_id_or_harness_change_preserves_previously_chosen_root_and_prepare_provenance(tmp_path, monkeypatch, choice, value):
    from okto_nexus.adapters.inbound.cli import quick_connect_selection as selection
    args, document = reviewed(tmp_path)
    invocation = tmp_path / 'A'
    chosen = tmp_path / 'B'
    invocation.mkdir()
    chosen.mkdir()
    args.project = None
    document['selection']['project'] = str(chosen)
    provenance = dict(invocation_cwd=str(invocation), project_root=str(chosen),
        root_explicit=False, source='existing_nexus')
    document['selection']['quick_connect']['cwd_resolution'] = provenance
    answers = iter([choice, value])
    restart = customize(args, [], document, invocation_cwd=str(invocation),
        read=lambda _: next(answers), write=lambda _: None)
    updated, _ = parse_connect_args(restart.argv)
    assert updated.project == chosen and restart.invocation_cwd == str(invocation)
    assert restart.frozen_name['cwd_resolution'] == provenance
    monkeypatch.setattr(selection, 'local_executor', lambda *_: 'executor')
    monkeypatch.setattr(selection, 'require_public_ids', lambda *_: None)
    monkeypatch.setattr(selection, 'public_ids', lambda *a, **k: ())
    monkeypatch.setattr(selection, 'choose_harness', lambda *a, **k: (updated.client, 'candidate'))
    def resolve(_call, **kwargs):
        assert kwargs['root'] == str(chosen) and kwargs['invocation_cwd'] == str(invocation)
        hint = kwargs['discover'](chosen, plan=False)
        assert hint.name == 'Saved Git name'
        return dict(label=hint.name, workspace_id='canonical-workspace', project=str(chosen),
            project_revision='sha256:' + 'a' * 64, project_name_source='explicit',
            name_discovery=dict(status='not_needed', reason='explicit_name'),
            cwd_resolution=dict(provenance, root_explicit=True, source='explicit_project'))
    monkeypatch.setattr(selection, 'resolve_project', resolve)
    from okto_nexus.adapters.outbound import git_project_hint
    monkeypatch.setattr(git_project_hint, 'discover_project_name', lambda *a, **k: pytest.fail('no Git rediscovery'))
    result = selection.prepare(lambda *a: dict(server_id='server', agent_id='operator'), updated,
        root=str(chosen), invocation_cwd=str(invocation), frozen_name=restart.frozen_name)
    assert result['selection']['project'] == str(chosen)
    assert result['selection']['workspace_id'] == 'canonical-workspace'
    assert result['selection']['quick_connect']['cwd_resolution'] == provenance
    assert result['selection']['quick_connect']['project_name_source'] == 'git_origin'


@pytest.mark.parametrize('selector', ['--workspace-id', '--binding-id', '--agent'])
@pytest.mark.parametrize('choice', ['2', '4'])
def test_exact_tuple_cannot_be_silently_retargeted(tmp_path, selector, choice):
    args, document = reviewed(tmp_path, selector, 'exact')
    before = deepcopy(document)
    with pytest.raises(ConnectionError) as caught:
        change(args, document, choice, str(tmp_path))
    assert caught.value.code == 'CONNECTION_SELECTOR_CONFLICT'
    assert document == before


@pytest.mark.parametrize('selector', ['--binding-id', '--agent'])
def test_existing_identity_cannot_change_harness(tmp_path, selector):
    args, document = reviewed(tmp_path, selector, 'exact')
    with pytest.raises(ConnectionError) as caught:
        change(args, document, '3', 'claude')
    assert caught.value.code == 'CONNECTION_SELECTOR_CONFLICT'


def test_association_changes_only_public_id_and_retains_exact_identity(tmp_path):
    args, document = reviewed(tmp_path, association=True)
    result = change(args, document, '1', 'associated')
    updated, _ = parse_connect_args(result.argv)
    assert (updated.agent, updated.binding_id, updated.workspace_id) == ('existing-agent', 'existing-binding', 'canonical-workspace')
    assert not updated.new_connection and updated.connect_id == 'associated' and updated.approve is None
    with pytest.raises(ConnectionError):
        change(args, document, '3', 'claude')


@pytest.mark.parametrize('choice', ['', 'c', 'C'])
def test_cancel_does_not_create_profile_or_mutate_review(tmp_path, monkeypatch, choice):
    args, document = reviewed(tmp_path)
    before = deepcopy(document)
    import okto_nexus.adapters.inbound.cli.quick_connect_customize as module
    monkeypatch.setattr(module.uuid, 'uuid4', lambda: pytest.fail('cancel must not generate identity'))
    assert change(args, document, choice) is None
    assert document == before


def test_eof_before_or_after_field_selection_cancels(tmp_path):
    args, document = reviewed(tmp_path)
    for answers in ([], ['1']):
        values = iter(answers)
        def read(_):
            try:
                return next(values)
            except StopIteration:
                raise EOFError from None
        assert customize(args, [], document, invocation_cwd='original', read=read, write=lambda _: None) is None


@pytest.mark.parametrize('choice,value', [('1', '../invalid'), ('2', ''), ('2', 'bad\nname')])
def test_invalid_values_do_not_mutate_review(tmp_path, choice, value):
    args, document = reviewed(tmp_path)
    before = deepcopy(document)
    with pytest.raises((ValueError, ConnectionError)):
        change(args, document, choice, value)
    assert document == before


def test_restart_trampoline_reenters_only_after_previous_invocation_unwinds(monkeypatch):
    from okto_nexus.adapters.inbound.cli import connect
    events = []
    def once(argv, *, invocation_cwd, frozen_name):
        events.append(('enter', argv, invocation_cwd, frozen_name))
        try:
            if argv == ['original']:
                raise ReviewRestart(['replacement'], 'captured-cwd', {'name': 'frozen'})
            assert events[-2] == ('released', ['original'])
            return 0
        finally:
            events.append(('released', argv))
    monkeypatch.setattr(connect, '_run_connect_once', once)
    assert connect.run_connect(['original']) == 0
    assert events[2] == ('enter', ['replacement'], 'captured-cwd', {'name': 'frozen'})


def test_json_allowlist_does_not_expose_or_mutate_unknown_private_members(tmp_path):
    _, document = reviewed(tmp_path)
    document['private_future_member'] = {'secret': 'never-echo'}
    document['selection']['private_future_selector'] = {'secret': 'never-echo'}
    document['selection']['quick_connect']['project_name_source'] = 'git_origin'
    before = deepcopy(document)
    result = public_wire(document)
    assert 'private_future_member' not in result and 'private_future_selector' not in result['selection']
    assert result['selection']['public_connection'] == document['selection']['public_connection']
    assert document == before


def test_legacy_document_wire_is_unchanged():
    document = dict(state='review', selection=dict(legacy_future_member='retained'))
    assert public_wire(document) is document


def test_association_commit_retains_private_future_selection_without_echoing_it():
    """Unit port boundary only: canonical association acceptance is covered separately."""
    from types import SimpleNamespace
    from okto_nexus.application.terminal_connection import TerminalConnection, document_revision
    reference = dict(server_id='s', executor_id='e', binding_id='b', endpoint_id='ep',
        agent_id='a', workspace_id='w', workspace_binding_id='wb')
    public = dict(state='bound', connect_id='new-id', canonical_ref=reference)
    previous = dict(client='codex', agent='a', binding_id='b', private_future_selector={'opaque': 'keep'})
    selection = dict(client='codex', agent='a', binding_id='b', public_connection=dict(connect_id='new-id'),
        quick_connect=dict(operation='associated_existing'))
    request = dict(connect_id='new-id', expected_binding_ref=reference)
    review = dict(server_id='s', selection=selection, request=request, version_check_required=False, effects=[])
    document = dict(review, kind='public_id_association', state='review', review_request=deepcopy(request),
        review_revision=document_revision(review), public_id_previous_setup=dict(selection=deepcopy(previous)),
        private_future_member={'opaque': 'keep-top'})
    saved, calls = [], []
    def api(method, path, body):
        calls.append((method, path, deepcopy(body)))
        return deepcopy(public)
    port = SimpleNamespace(api=api, save=lambda d: saved.append(deepcopy(d)),
        _save_committed=lambda d: saved.append(deepcopy(d)), observe=lambda d: deepcopy(d))
    result = TerminalConnection._apply_public_association(port, document, document['review_revision'])
    assert len(calls) == 1 and calls[0][1] == '/connections/public-ids/associate-existing'
    assert result['state'] == 'done' and result['selection']['public_connection']['connect_id'] == 'new-id'
    assert result['selection']['private_future_selector'] == previous['private_future_selector']
    assert result['private_future_member'] == {'opaque': 'keep-top'}
    assert saved[-1] == result and previous['private_future_selector'] == {'opaque': 'keep'}
    wire = public_wire(result)
    assert 'private_future_selector' not in wire['selection'] and 'private_future_member' not in wire
