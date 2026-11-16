"""Real parser/store/locks, explicit fake HTTP/setup boundaries, no processes."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.inbound.cli.connection_choices import ConnectionChoiceCatalog
from okto_nexus.adapters.inbound.cli.connection_picker import pick_connection, pick_harness
from okto_nexus.adapters.inbound.cli.connection_reservation import pending_reservations, read_reservation, reserve_connection
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
from okto_nexus.application.terminal_connection import ConnectionError


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    home, project = tmp_path / 'home', tmp_path / 'project'
    project.mkdir()
    calls = []
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=12345),
        inspect=lambda: calls.append('inspect') or {'state': 'ready', 'instance_id': 'instance-a'},
        ensure_running=lambda **k: calls.append('ensure') or {'state': 'ready', 'instance_id': 'instance-a'})
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    def http(*args, **kwargs):
        def call(method, path, body=None):
            assert method == 'GET'
            def catalog_rows():
                rows = []
                for source in (home / 'terminal/profiles').glob('*.json'):
                    document = read_json(source)
                    selected = document['selection']
                    binding = document.get('result', {}).get('binding', {})
                    if not binding.get('binding_id'):
                        continue
                    rows.append(dict(server_id='server-a', binding_id=binding['binding_id'],
                        endpoint_id='endpoint-' + selected['agent'], executor_id='executor-a',
                        agent_id=selected['agent'], workspace_id=selected.get('workspace_id') or 'workspace-existing',
                        workspace_binding_id='workspace-binding-' + selected['agent'],
                        adapter_id={'codex': 'codex_app_server', 'claude': 'claude_stream'}[selected['client']],
                        execution_location='local'))
                return rows
            if '/connections/catalog?' in path:
                from urllib.parse import parse_qs, urlsplit
                query = parse_qs(urlsplit(path).query)
                scope = {'execution_location': 'local'}
                if 'workspace_id' in query:
                    scope['workspace_id'] = query['workspace_id'][0]
                rows = [row for row in catalog_rows() if scope.get('workspace_id') in (None, row['workspace_id'])]
                return dict(version=1, server_id='server-a', scope=scope, revision='a' * 64,
                    items=rows, total=len(rows), total_is_exact=True, has_more=False, next_cursor=None)
            if '/connections/bindings/' in path:
                binding_id = path.rsplit('/', 1)[-1]
                return next(row for row in catalog_rows() if row['binding_id'] == binding_id) | {'state': 'APPROVED'}
            if '/connections/setup/' in path:
                from urllib.parse import unquote, urlsplit
                agent = unquote(urlsplit(path).path.rsplit('/', 1)[-1])
                documents = [read_json(p) for p in (home / 'terminal/profiles').glob('*.json')]
                selected = next(d for d in documents if d['selection']['agent'] == agent)
                workspace = selected['selection'].get('workspace_id') or 'workspace-existing'
                return {'connections': [dict(binding_id=selected['result']['binding']['binding_id'],
                    workspace_id=workspace, execution_location='local')],
                    'folders': dict(workspace_root=str(project), workspace_label='Approved project')}
            assert path.endswith('/connections/me')
            calls.append('me')
            return {'server_id': 'server-a'}
        return call
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', http)
    state = SimpleNamespace(fail_review=False, fail_apply=False, enrich=False, review_server='server-a')
    class Flow:
        def __init__(self, call, save):
            self.save = save
        def review(self, selection):
            calls.append(('review', deepcopy(selection)))
            if 'setup_intent_id' in selection:
                reservations = list((home / 'terminal/connection-intents').glob('*.json'))
                assert any(read_json(p)['selection'] == selection for p in reservations)
            if state.fail_review:
                raise ConnectionError('FAKE_HTTP_UNAVAILABLE', 'Before review response')
            if state.enrich:
                selection['client'] = selection.get('client') or 'codex'
                selection['provider_home'] = selection.get('provider_home') or '/resolved-by-reviewed-inventory'
            document = dict(format=1, state='review', server_id=state.review_server, selection=selection,
                review_revision='revision', effects=[], version_check_required=False,
                request=dict(client_intent_id=selection.get('setup_intent_id', 'old-setup-id'),
                    agent_id=selection['agent'], workspace_id=selection.get('workspace_id'),
                    configuration=dict(adapter_id=selection['client'], workspace_root=str(project),
                        workspace_label='Project', provider_home=None)))
            self.save(document)
            return document
        def apply(self, document, **kwargs):
            if state.fail_apply:
                document['state'] = 'test_submitted'
                self.save(document)
                raise ConnectionError('OUTCOME_UNKNOWN', 'Fake lost setup response', possible_effect=True)
            calls.append(('apply', document['request']['client_intent_id']))
            document.update(state='done', result={'binding': {'binding_id': 'binding-a'}})
            self.save(document)
            return self.observe(document)
        def observe(self, document):
            calls.append(('observe', document['selection']['agent']))
            return dict(state='configured', agent_id=document['selection']['agent'],
                workspace_id='workspace-a', binding_id='binding-a')
    monkeypatch.setattr(connect, 'TerminalConnection', Flow)
    monkeypatch.setattr(connect.sys.stdin, 'isatty', lambda: False)
    def run(*args):
        return connect.run_connect(['--home', str(home), '--project', str(project), *args])
    return SimpleNamespace(home=home, project=project, calls=calls, state=state, run=run)


def existing(b, name='legacy', client='codex'):
    directory = b.home / 'terminal/profiles'
    directory.mkdir(parents=True, exist_ok=True)
    value = dict(format=1, state='done', server_id='server-a',
        selection=dict(agent='agent-' + name, client=client, project=str(b.project)),
        result={'binding': {'binding_id': 'binding-' + name}})
    atomic_json(directory / (name + '.json'), value)
    return directory / (name + '.json')


def tty(monkeypatch, answers):
    monkeypatch.setattr(connect.sys.stdin, 'isatty', lambda: True)
    it = iter(answers)
    monkeypatch.setattr('builtins.input', lambda prompt: next(it))


def test_json_ambiguous_returns_selection_without_setup(boundary, capsys):
    b = boundary
    existing(b, 'one')
    existing(b, 'two', 'claude')
    assert b.run('--json') == 3
    value = json.loads(capsys.readouterr().out)
    assert value['state'] == 'selection_required' and len(value['choices']) == 2
    assert value['effects_started'] is None and value['lifecycle_requested']
    assert not any(isinstance(c, tuple) for c in b.calls)


def test_plan_selection_and_cancel_never_start_service(boundary, monkeypatch, capsys):
    b = boundary
    path = existing(b)
    before = path.read_bytes()
    tty(monkeypatch, ['c'])
    assert b.run('--plan') == 0
    assert 'canceled' in capsys.readouterr().out
    assert 'ensure' not in b.calls and path.read_bytes() == before
    assert not (b.home / 'terminal/connection-intents').exists()


def test_resume_exact_connection_no_defaults_or_grants(boundary, monkeypatch):
    b = boundary
    a, z = existing(b, 'a'), existing(b, 'z')
    before = a.read_bytes(), z.read_bytes()
    tty(monkeypatch, ['2'])
    assert b.run('--no-chat') == 0
    assert ('observe', 'agent-z') in b.calls
    assert not any(isinstance(c, tuple) and c[0] in {'review', 'apply'} for c in b.calls)
    assert (a.read_bytes(), z.read_bytes()) == before


@pytest.mark.parametrize('race', ['deleted', 'replaced'])
def test_selected_connection_race_never_becomes_new_setup(boundary, monkeypatch, race):
    b = boundary
    path = existing(b)
    monkeypatch.setattr(connect.sys.stdin, 'isatty', lambda: True)
    def choose(prompt):
        if race == 'deleted':
            path.unlink()
        else:
            value = read_json(path)
            value['selection']['agent'] = 'replacement-agent'
            atomic_json(path, value)
        return '1'
    monkeypatch.setattr('builtins.input', choose)
    assert b.run('--no-chat') == 3
    assert not any(isinstance(c, tuple) and c[0] in {'review', 'apply', 'observe'} for c in b.calls)
    assert not (b.home / 'terminal/connection-intents').exists()


def test_second_harness_generated_profile_keeps_original(boundary, monkeypatch):
    b = boundary
    original = existing(b)
    before = original.read_bytes()
    tty(monkeypatch, ['a'])
    assert b.run('--client', 'claude', '--plan') == 0
    assert original.read_bytes() == before
    added, = list((b.home / 'terminal/connection-intents').glob('*.json'))
    reservation = read_json(added)
    assert reservation['selection']['client'] == 'claude'
    assert reservation['selection']['agent'] != 'agent-legacy'
    assert reservation['selection']['workspace_id'] == 'workspace-existing'
    assert read_json(b.home / 'terminal/profiles' / added.name)['request']['workspace_id'] == 'workspace-existing'
    assert (b.home / 'terminal/profiles' / added.name).exists()


def test_script_multiple_projects_requires_workspace_id_and_preserves_explicit_choice(boundary, capsys):
    b = boundary
    for name, workspace in [('a', 'workspace-a'), ('b', 'workspace-b')]:
        path = existing(b, name)
        value = read_json(path)
        value['selection']['workspace_id'] = workspace
        atomic_json(path, value)
    args = ('--new-connection', '--profile', 'new', '--client', 'claude', '--plan', '--json')
    assert b.run(*args) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'workspace_selection_required'
    assert {row['workspace_id'] for row in result['choices']} == {'workspace-a', 'workspace-b'}
    assert not (b.home / 'terminal/connection-intents').exists()
    assert b.run(*args, '--workspace-id', 'workspace-b') == 0
    assert read_json(b.home / 'terminal/profiles/new.json')['request']['workspace_id'] == 'workspace-b'


def test_interactive_multiple_projects_are_chosen_explicitly(boundary, monkeypatch):
    b = boundary
    for name, workspace in [('a', 'workspace-a'), ('b', 'workspace-b')]:
        path = existing(b, name)
        value = read_json(path)
        value['selection']['workspace_id'] = workspace
        atomic_json(path, value)
    tty(monkeypatch, ['a', '2'])
    assert b.run('--client', 'claude', '--plan') == 0
    added, = (b.home / 'terminal/connection-intents').glob('*.json')
    assert read_json(added)['selection']['workspace_id'] == 'workspace-b'


def test_new_script_requires_stable_profile_before_service(boundary, capsys):
    assert boundary.run('--new-connection', '--json') == 3
    value = json.loads(capsys.readouterr().out)
    assert value['effects_started'] is False
    assert boundary.calls == [] and not boundary.home.exists()


def test_new_intent_retry_before_review_retains_agent_and_setup_id(boundary):
    b = boundary
    b.state.fail_review = True
    args = ('--new-connection', '--profile', 'new', '--client', 'claude', '--plan', '--json')
    assert b.run(*args) == 3
    retained = read_reservation(b.home, 'new')
    b.state.fail_review = False
    assert b.run(*args) == 0
    current = read_json(b.home / 'terminal/profiles/new.json')
    assert current['selection'] == retained['selection']
    assert current['request']['client_intent_id'] == retained['client_intent_id']
    assert read_reservation(b.home, 'new') == retained


def test_pre_review_reservation_visible_and_recoverable_without_new_flag(boundary, monkeypatch):
    b = boundary
    b.state.fail_review = True
    assert b.run('--new-connection', '--profile', 'new', '--client', 'claude', '--plan', '--json') == 3
    catalog = pending_reservations(b.home, str(b.project), 'server-a')
    assert catalog.complete and catalog.choices[0].profile == 'new'
    retained = read_reservation(b.home, 'new')
    b.state.fail_review = False
    tty(monkeypatch, ['1'])
    assert b.run('--plan') == 0
    assert read_json(b.home / 'terminal/profiles/new.json')['selection'] == retained['selection']


def test_after_review_response_loss_keeps_checkpoint_and_explicit_profile_compatibility(boundary):
    b = boundary
    args = ('--new-connection', '--profile', 'new', '--client', 'codex', '--json')
    b.state.fail_apply = True
    assert b.run(*args, '--approve', 'revision') == 3
    checkpoint = read_json(b.home / 'terminal/profiles/new.json')
    assert checkpoint['state'] == 'test_submitted'
    b.state.fail_apply = False
    assert b.run('--profile', 'new', '--json') == 0
    assert ('apply', checkpoint['request']['client_intent_id']) in b.calls


def test_review_enrichment_is_retained_without_rewriting_original_intent(boundary):
    b = boundary
    b.state.enrich = True
    assert b.run('--new-connection', '--profile', 'new', '--plan', '--json') == 0
    original = read_reservation(b.home, 'new')
    assert original['selection']['client'] is None
    document = read_json(b.home / 'terminal/profiles/new.json')
    assert document['selection']['client'] == 'codex'
    assert b.run('--new-connection', '--profile', 'new', '--plan', '--json') == 0
    assert read_reservation(b.home, 'new') == original


def test_server_changed_during_review_refuses_before_apply_and_preserves_reservation(boundary):
    b = boundary
    b.state.review_server = 'server-b'
    assert b.run('--new-connection', '--profile', 'new', '--client', 'codex', '--approve', 'revision', '--json') == 3
    retained = read_reservation(b.home, 'new')
    assert retained['server_id'] == 'server-a'
    assert not (b.home / 'terminal/profiles/new.json').exists()
    assert not any(isinstance(c, tuple) and c[0] == 'apply' for c in b.calls)


def test_explicit_client_conflict_and_legacy_new_flag_do_not_overwrite(boundary):
    b = boundary
    old = existing(b)
    before = old.read_bytes()
    assert b.run('--profile', 'legacy', '--client', 'claude', '--json') == 3
    assert b.run('--new-connection', '--profile', 'legacy', '--json') == 3
    assert old.read_bytes() == before
    assert not (b.home / 'terminal/connection-intents').exists()


def test_changed_addition_choices_refused_and_profile_busy_preserves_intent(boundary):
    b = boundary
    assert b.run('--new-connection', '--profile', 'new', '--client', 'codex', '--plan', '--json') == 0
    path = b.home / 'terminal/profiles/new.json'
    before = path.read_bytes()
    assert b.run('--new-connection', '--profile', 'new', '--client', 'claude', '--json') == 3
    lock = ExclusiveFileLock(path.with_suffix('.guard'))
    lock.acquire()
    try:
        assert b.run('--profile', 'new', '--json') == 3
    finally:
        lock.release()
    assert path.read_bytes() == before


def test_remote_new_flag_rejected_before_operator_client_or_local_fallback(boundary, monkeypatch):
    from okto_nexus.adapters.inbound.cli import terminal_target
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *args: pytest.fail('must not open operator client'))
    assert boundary.run('--operator-profile', 'remote', '--new-connection', '--profile', 'new', '--json') == 3
    assert boundary.calls == []


def test_empty_catalog_picker_does_not_ask_for_profile():
    assert pick_connection(ConnectionChoiceCatalog((), (), True), read=lambda p: pytest.fail('no profile prompt')) == ('add', None)


def test_harness_picker_only_uses_observed_options():
    answers = iter(['pi', '0', '2'])
    assert pick_harness(['codex', 'claude'], read=lambda p: next(answers), write=lambda p: None) == 'claude'
    assert pick_harness(['codex'], read=lambda p: '', write=lambda p: None) is None


def test_concurrent_additions_same_profile_cannot_overwrite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from okto_nexus.adapters.outbound.service_manager.locking import LockBusy
    directory = tmp_path / 'terminal/profiles'
    directory.mkdir(parents=True)
    barrier = Barrier(2)
    def attempt(agent):
        guard = ExclusiveFileLock(directory / 'new.guard')
        barrier.wait(timeout=5)
        try:
            guard.acquire()
            return reserve_connection(tmp_path, 'new',
                dict(agent=agent, project=str(tmp_path), create_agent=True), 'server-a')
        except (LockBusy, ConnectionError):
            return None
        finally:
            guard.release()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['a', 'b']))
    assert sum(result is not None for result in results) == 1
    retained = read_reservation(tmp_path, 'new')
    assert retained in results


def test_pending_other_harness_is_visible_before_independent_addition(boundary, monkeypatch):
    b = boundary
    path = existing(b, 'pending')
    value = read_json(path)
    value['state'] = 'test_submitted'
    atomic_json(path, value)
    before = path.read_bytes()
    tty(monkeypatch, ['a'])
    assert b.run('--client', 'claude', '--plan') == 0
    assert path.read_bytes() == before
    assert any(isinstance(call, tuple) and call[0] == 'review'
        and call[1]['agent'] != 'agent-pending' for call in b.calls)


@pytest.mark.parametrize('profile', ['../outside', 'a/b', 'a\\b', '', '.', '..'])
def test_direct_reservation_api_rejects_profile_paths_before_creation(tmp_path, profile):
    home = tmp_path / 'absent'
    with pytest.raises(ConnectionError, match='simple local profile'):
        read_reservation(home, profile)
    with pytest.raises(ConnectionError, match='simple local profile'):
        reserve_connection(home, profile, {'agent': 'new'}, 'server-a')
    assert not home.exists()


def test_reservation_idempotence_accepts_original_selection_without_setup_id(tmp_path):
    selection = dict(agent='new', project=str(tmp_path), create_agent=True)
    first = reserve_connection(tmp_path, 'new', selection, 'server-a')
    assert reserve_connection(tmp_path, 'new', selection, 'server-a') == first
    assert reserve_connection(tmp_path, 'new', first['selection'], 'server-a') == first
    with pytest.raises(ConnectionError):
        reserve_connection(tmp_path, 'new', selection | {'agent': 'other'}, 'server-a')


@pytest.mark.parametrize('redirect', ['terminal', 'connection-intents', 'profiles'])
def test_redirected_parent_cannot_create_outside_store(tmp_path, redirect):
    home, outside = tmp_path / 'home', tmp_path / 'outside'
    home.mkdir()
    outside.mkdir()
    sentinel = outside / 'sentinel.txt'
    sentinel.write_bytes(b'unchanged')
    if redirect == 'terminal':
        link = home / 'terminal'
    else:
        (home / 'terminal').mkdir()
        link = home / 'terminal' / redirect
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip('Directory symlink creation unavailable: ' + str(error))
    before = {str(p.relative_to(outside)): p.read_bytes() for p in outside.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        reserve_connection(home, 'new', {'agent': 'new'}, 'server-a')
    with pytest.raises(ValueError):
        read_reservation(home, 'new')
    assert not pending_reservations(home, str(tmp_path), 'server-a').complete
    assert {str(p.relative_to(outside)): p.read_bytes() for p in outside.rglob('*') if p.is_file()} == before
    assert list(outside.iterdir()) == [sentinel]


def test_cli_explicit_addition_checks_redirect_before_profile_lock(boundary):
    b = boundary
    outside = b.project / 'outside'
    outside.mkdir()
    b.home.mkdir()
    try:
        (b.home / 'terminal').symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip('Directory symlink creation unavailable: ' + str(error))
    assert b.run('--new-connection', '--profile', 'new', '--json') == 3
    assert list(outside.iterdir()) == []
    assert b.calls == []
