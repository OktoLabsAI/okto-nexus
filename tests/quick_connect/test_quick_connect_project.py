"""Project resolver contracts over fake authorized GETs and real temporary dirs.

These are client semantic tests, not SQLite, HTTP authority or race transaction
proofs. No Git process is started: injected hints are already-qualified DTOs.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from okto_nexus.adapters.inbound.cli import quick_connect_project as projects
from okto_nexus.adapters.outbound.git_project_hint import GitProjectHint
from okto_nexus.application.terminal_connection import ConnectionError, PREFIX
from okto_nexus.domain.quick_connect import CwdResolution, NameDiscovery


def no_read(_):
    pytest.fail('unexpected interactive read')


def no_discover(*_args, **_kwargs):
    pytest.fail('exact canonical or explicit selection must not invoke Git discovery')


def assert_code(code, action):
    with pytest.raises(ConnectionError) as captured:
        action()
    assert captured.value.code == code


def workspace(key, name):
    return dict(workspace_id=key, display_name=name)


def directory(items=(), *, total=None, more=False, cursor=None, revision='a' * 64):
    return dict(version=1, server_id='server-a', items=list(items), total=len(items) if total is None else total,
                total_is_exact=True, has_more=more, next_cursor=cursor, revision=revision)


class CanonicalReads:
    def __init__(self, root, items=(), *, mapped=(), paths=None):
        self.root = str(root)
        self.items, self.mapped = list(items), list(mapped)
        self.paths = paths or {}
        self.calls = []
        self.revision = 'a' * 64
        self.before = None

    def __call__(self, method, path):
        assert method == 'GET', 'resolver must never mutate workspace, agent, service or setup'
        self.calls.append((method, path))
        if self.before:
            self.before(self, path)
        parsed = urlsplit(path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        route = parsed.path.removeprefix(PREFIX)
        if route == '/connections/workspaces':
            return directory(deepcopy(self.items), revision=self.revision)
        if route == '/connections/project-context':
            return dict(version=1, server_id='server-a', executor_id=query['executor_id'],
                        project_root=query['project_root'], workspace_id=query.get('workspace_id'),
                        project_revision='sha256:' + 'b' * 64,
                        mapped_workspace_ids=deepcopy(self.mapped), mappings=[], association=None)
        if route.startswith('/workspaces/') and route.endswith('/paths'):
            key = route.split('/')[2]
            return dict(workspace_id=key, executor_id=query['executor_id'],
                        items=[{'path': str(p)} for p in self.paths.get(key, [])])
        pytest.fail('unexpected canonical GET route: ' + route)


def resolve(call, root, **kwargs):
    return projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(root), root=str(root), read=no_read, discover=no_discover, **kwargs)


def test_unique_exact_mapping_reuses_project_without_git_or_picker(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'Existing')], mapped=['w-a'])
    result = resolve(call, tmp_path)
    assert (result['workspace_id'], result['label'], result['project_name_source']) == ('w-a', 'Existing', 'existing_nexus')
    assert result['project'] == str(tmp_path)
    assert NameDiscovery(**result['name_discovery']).reason == 'existing_nexus'
    assert CwdResolution(**result['cwd_resolution']).invocation_cwd == str(tmp_path)


def test_explicit_label_selects_project_without_binding(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'app')])
    result = resolve(call, tmp_path, project_name='app')
    assert result['workspace_id'] == 'w-a' and result['project'] == str(tmp_path)
    assert result['project_name_source'] == 'explicit'


def test_new_explicit_label_is_proposal_not_path_or_workspace_creation(tmp_path):
    call = CanonicalReads(tmp_path)
    result = resolve(call, tmp_path, project_name='Minha aplicação')
    assert result['workspace_id'] is None and result['label'] == 'Minha aplicação'
    assert not (tmp_path / 'Minha aplicação').exists()
    assert all(method == 'GET' for method, _ in call.calls)


@pytest.mark.parametrize('interactive', [False, True])
def test_exact_workspace_and_conflicting_label_never_override_each_other(tmp_path, interactive):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'A'), workspace('w-b', 'B')])
    assert_code('PROJECT_SELECTOR_CONFLICT', lambda: resolve(call, tmp_path, workspace_id='w-a',
                project_name='B', interactive=interactive))


def test_exact_workspace_and_agreeing_name_preserve_selector(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'A'), workspace('w-b', 'B')], mapped=['w-a'])
    assert resolve(call, tmp_path, workspace_id='w-a', project_name='A')['workspace_id'] == 'w-a'


def test_duplicate_names_require_choice_noninteractive(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'app'), workspace('w-b', 'app')])
    assert_code('PROJECT_SELECTION_REQUIRED', lambda: resolve(call, tmp_path, project_name='app'))


def test_duplicate_names_tty_choice_is_exact(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'app'), workspace('w-b', 'app')])
    output = []
    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(tmp_path), root=str(tmp_path), project_name='app', interactive=True,
        read=lambda _: '2', write=output.append, discover=no_discover)
    assert result['workspace_id'] == 'w-b'
    assert any('w-a' in text for text in output) and any('w-b' in text for text in output)


@pytest.mark.parametrize('explicit,interactive', [(True, True), (True, False), (False, False)])
def test_different_approved_root_requires_explicit_resolution(tmp_path, explicit, interactive):
    other = tmp_path / 'other'
    other.mkdir()
    call = CanonicalReads(tmp_path, [workspace('w-b', 'B')], paths={'w-b': [other]})
    assert_code('PROJECT_DIRECTORY_MISMATCH', lambda: resolve(call, tmp_path,
        workspace_id='w-b', explicit_root=explicit, interactive=interactive))


def test_tty_switch_root_records_provenance_without_chdir(tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    before = Path.cwd()
    call = CanonicalReads(tmp_path, [workspace('w-b', 'B')], paths={'w-b': [other]})
    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(tmp_path), root=str(tmp_path), workspace_id='w-b', interactive=True,
        read=lambda _: '1', write=lambda _: None, discover=no_discover)
    assert result['project'] == str(other) and Path.cwd() == before
    assert result['cwd_resolution'] == dict(invocation_cwd=str(tmp_path), project_root=str(other),
                                          root_explicit=False, source='existing_nexus')


def test_explicit_root_preserves_original_invocation_cwd(tmp_path):
    other = tmp_path / 'explicit'
    other.mkdir()
    call = CanonicalReads(other)
    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(tmp_path), root=str(other), explicit_root=True,
        project_name='app', read=no_read, discover=no_discover)
    assert result['project'] == str(other)
    assert result['cwd_resolution'] == dict(invocation_cwd=str(tmp_path), project_root=str(other),
                                          root_explicit=True, source='explicit_project')


def test_hint_does_not_inherit_parent_mapping_or_merge_equal_names(tmp_path):
    sub = tmp_path / 'apps' / 'api'
    sub.mkdir(parents=True)
    call = CanonicalReads(sub, [workspace('parent', 'monorepo')])
    seen = []

    def discover(root, *, plan):
        seen.append((root, plan))
        return GitProjectHint('monorepo', 'git_origin', 'discovered', 'git_origin')

    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(sub), root=str(sub), read=no_read, discover=discover)
    assert result['workspace_id'] is None and result['project'] == str(sub)
    assert result['label'] == 'monorepo' and seen == [(sub, False)]


def test_catalog_choice_after_hint_keeps_existing_nexus_source(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'Existing')])
    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(tmp_path), root=str(tmp_path), interactive=True,
        read=lambda _: '1', write=lambda _: None,
        discover=lambda *_a, **_k: GitProjectHint('suggestion', 'directory', 'fallback', 'directory_fallback'))
    assert result['workspace_id'] == 'w-a' and result['project_name_source'] == 'existing_nexus'
    assert result['name_discovery']['reason'] == 'existing_nexus'


def test_plan_passes_no_process_flag_and_only_proposes_directory_name(tmp_path):
    call = CanonicalReads(tmp_path)
    flags = []

    def discover(root, *, plan):
        flags.append(plan)
        return GitProjectHint(root.name, 'directory', 'not_run_plan', 'not_run_plan')

    result = projects.resolve_project(call, server_id='server-a', executor_id='host-a',
        invocation_cwd=str(tmp_path), root=str(tmp_path), plan=True, discover=discover, read=no_read)
    assert result['workspace_id'] is None and flags == [True]
    assert result['name_discovery'] == {'status': 'not_run_plan', 'reason': 'not_run_plan'}


def test_explicit_or_existing_name_precedes_changed_git_hint(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'Old project')], mapped=['w-a'])
    assert resolve(call, tmp_path)['label'] == 'Old project'
    empty = CanonicalReads(tmp_path)
    assert resolve(empty, tmp_path, project_name='explicit')['label'] == 'explicit'


def test_unknown_mapping_is_not_an_empty_catalog(tmp_path):
    call = CanonicalReads(tmp_path, mapped=['unauthorized-or-absent'])
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: resolve(call, tmp_path))


def test_catalog_rename_between_selection_and_return_requires_new_review(tmp_path):
    call = CanonicalReads(tmp_path, [workspace('w-a', 'Before')], mapped=['w-a'])

    def mutate(reader, path):
        if '/project-context?' in path and 'workspace_id=w-a' in path:
            reader.items[0]['display_name'] = 'After'
            reader.revision = 'c' * 64

    call.before = mutate
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: resolve(call, tmp_path))


@pytest.mark.parametrize('patch', [
    {'version': 2}, {'server_id': 'server-b'}, {'revision': 'short'}, {'revision': 'z' * 64},
    {'items': None}, {'items': [{}] * 101}, {'has_more': 1}, {'total_is_exact': False},
    {'total': True}, {'total': 1}, {'next_cursor': 'unexpected'},
])
def test_invalid_directory_envelope_cannot_authorize_new_project(patch):
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_directory(
        lambda *_: directory() | patch, 'server-a'))


@pytest.mark.parametrize('items', [[workspace('', 'app')], [workspace('w-a', 'app'), workspace('w-a', 'other')],
                                  [workspace('w-a', '\x1bprivate')], [workspace('w-a', '')]])
def test_invalid_or_duplicate_directory_metadata_fails_closed(items):
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_directory(
        lambda *_: directory(items), 'server-a'))


def test_pagination_complete_and_revision_drift(tmp_path):
    pages = iter([directory([workspace('a', 'A')], more=True, cursor='page2', total=2),
                  directory([workspace('b', 'B')], total=2)])
    seen = []

    def call(method, path):
        assert method == 'GET'
        seen.append(path)
        return next(pages)

    rows, revision = projects.project_directory(call, 'server-a')
    assert [r['workspace_id'] for r in rows] == ['a', 'b'] and revision == 'a' * 64
    assert parse_qs(urlsplit(seen[-1]).query)['cursor'] == ['page2']
    pages = iter([directory([], more=True, cursor='next', total=1), directory([], revision='b' * 64, total=1)])
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_directory(lambda *_: next(pages), 'server-a'))


def test_nonadjacent_cursor_cycle_is_bounded():
    pages = iter([directory([], more=True, cursor=c, total=1) for c in ['a', 'b', 'a']])
    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_directory(lambda *_: next(pages), 'server-a'))


@pytest.mark.parametrize('patch', [
    {'server_id': 'server-b'}, {'executor_id': 'host-b'}, {'workspace_id': 'foreign'},
    {'project_root': 'relative'}, {'project_root': '/another/path'},
    {'project_revision': 'sha256:' + 'z' * 64}, {'mapped_workspace_ids': None},
])
def test_project_context_checks_full_echo_and_revision(tmp_path, patch):
    call = CanonicalReads(tmp_path)

    def altered(method, path):
        return call(method, path) | patch

    assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_context(altered,
        server_id='server-a', executor_id='host-a', root=str(tmp_path)))


@pytest.mark.parametrize('reader', ['directory', 'context'])
def test_null_wire_envelope_is_structured_unconfirmed(reader, tmp_path):
    if reader == 'directory':
        assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_directory(lambda *_: None, 'server-a'))
    else:
        assert_code('PROJECT_CATALOG_UNCONFIRMED', lambda: projects.project_context(lambda *_: None,
            server_id='server-a', executor_id='host-a', root=str(tmp_path)))


def test_paging_transport_failure_propagates_without_discovery_or_new_project(tmp_path):
    def denied(*_):
        raise ConnectionError('FORBIDDEN', 'Not authorized')

    assert_code('FORBIDDEN', lambda: resolve(denied, tmp_path))


def test_local_executor_pages_exactly_and_rejects_multiple_or_stale_hosts():
    pages = iter([{'items': [{'kind': 'remote', 'executor_id': 'remote'}], 'has_more': True, 'next_executor_id': 'remote'},
                  {'items': [{'kind': 'embedded', 'executor_id': 'host-a'}], 'has_more': False}])
    assert projects.local_executor(lambda *_: next(pages), 'operator') == 'host-a'
    assert_code('LOCAL_EXECUTOR_UNAVAILABLE', lambda: projects.local_executor(lambda *_: {
        'items': [{'kind': 'embedded', 'executor_id': 'a'}, {'kind': 'embedded', 'executor_id': 'b'}], 'has_more': False}, 'operator'))
