"""Prepare five external installed project-directory scenarios."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'qc20-git-boundary-scenarios'
old = Path(json.loads((PRIOR / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc23-directory-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
shutil.copyfile(PRIOR / 'package-ready.json', HERE / 'package-ready.json')
test = root / 'after/tests/quick_connect/test_quick_connect_project_directory_scenarios.py'
test.write_text('''"""Actual SQLite workspace directory + CLI selectors, no DTO replacement."""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from test_quick_connect_cli import (  # noqa: F401
    checking, invoke, isolated_provider_environment, local_setup, quick_cli, terminal,
)
from test_quick_connect_extra_scenarios import canonical_snapshot


def seed_workspace(c, workspace_id, label):
    # Use the installed canonical repository to seed metadata only. No runtime
    # binding, key, grant, session or project-root authority is introduced.
    from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteWorkspaceRepo
    with c.t.deps.connection_factory.unit_of_work() as uow:
        SqliteWorkspaceRepo(c.t.deps.clock).upsert(uow, workspace_id=workspace_id, display_name=label)


def duplicates(c):
    seed_workspace(c, 'qc23-duplicate-a', 'Same Logical Name')
    seed_workspace(c, 'qc23-duplicate-b', 'Same Logical Name')


def forbid_input(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda *args, **kwargs: pytest.fail('JSON prompted for input'))


def test_c05_duplicate_names_require_explicit_selection_not_first(quick_cli, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import connect
    c = quick_cli
    duplicates(c)
    before = canonical_snapshot(c)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts, displayed = [], []
    def answer(prompt):
        prompts.append(prompt)
        assert prompt == 'Project: '
        return '2'  # deliberately choose the second equal label
    original = connect._display
    def observe(value, json_mode):
        displayed.append(value)
        return original(value, json_mode)
    monkeypatch.setattr('builtins.input', answer)
    monkeypatch.setattr(connect, '_display', observe)
    assert c.run(['connect', 'codex', 'Same Logical Name', '--profile', 'duplicate-choice', '--plan', '--no-chat']) == 0
    text = capsys.readouterr().out
    assert 'qc23-duplicate-a' in text and 'qc23-duplicate-b' in text
    assert prompts == ['Project: ']
    review = displayed[-1]
    assert review['request']['workspace_id'] == 'qc23-duplicate-b'
    assert review['selection']['workspace_id'] == 'qc23-duplicate-b'
    assert review['selection']['project'] == str(c.project)
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []


def test_c06_exact_workspace_disambiguates_duplicate_names(quick_cli, monkeypatch, capsys):
    c = quick_cli
    duplicates(c)
    before = canonical_snapshot(c)
    forbid_input(monkeypatch)
    review = invoke(c, capsys, ['connect', 'codex', 'Same Logical Name', '--workspace-id', 'qc23-duplicate-b',
        '--profile', 'exact-duplicate', '--plan', '--json'])
    assert review['request']['workspace_id'] == 'qc23-duplicate-b'
    assert review['selection']['workspace_id'] == 'qc23-duplicate-b'
    assert review['selection']['project'] == str(c.project)
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []


def test_c07_disagreeing_explicit_name_and_workspace_refuse_without_prompt(quick_cli, monkeypatch, capsys):
    c = quick_cli
    duplicates(c)
    before = canonical_snapshot(c)
    forbid_input(monkeypatch)
    result = invoke(c, capsys, ['connect', 'codex', 'Different Name', '--workspace-id', 'qc23-duplicate-b',
        '--profile', 'disagreeing', '--plan', '--json'], expected=3)
    assert result['code'] == 'PROJECT_SELECTOR_CONFLICT'
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []
    assert Path.cwd() == c.project


def test_c08_explicit_project_b_is_used_by_finish_while_cwd_remains_a(quick_cli, monkeypatch, capsys):
    c = quick_cli
    root_a = c.project
    root_b = root_a / 'physical-b'
    root_b.mkdir()
    identity = (root_b.stat().st_dev, root_b.stat().st_ino)
    before = canonical_snapshot(c)
    forbid_input(monkeypatch)
    base = ['connect', 'codex', 'Logical Project B', '--project', str(root_b), '--profile', 'physical-b', '--json']
    review = invoke(c, capsys, [*base, '--plan'])
    assert review['selection']['project'] == str(root_b)
    assert review['request']['configuration']['workspace_root'] == str(root_b)
    resolution = review['quick_connect']['cwd_resolution']
    assert resolution['invocation_cwd'] == str(root_a)
    assert resolution['project_root'] == str(root_b) and resolution['root_explicit'] is True
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []
    configured = invoke(c, capsys, [*base, '--approve', review['review_revision']])
    assert configured['quick_connect']['project_root'] == str(root_b)
    assert configured['configuration']['folders']['workspace_root'] == str(root_b)
    reference = configured['quick_connect']['canonical_reference']
    assert len(reference) == 7 and reference['binding_id'] == configured['binding_id']
    assert Path.cwd() == root_a and identity == (root_b.stat().st_dev, root_b.stat().st_ino)
    assert not (root_b / 'Logical Project B').exists()
    after = canonical_snapshot(c)
    repeated = invoke(c, capsys, ['connect', '--profile', 'physical-b', '--json'])
    assert repeated['quick_connect']['canonical_reference'] == reference
    assert repeated['quick_connect']['cwd_resolution']['invocation_cwd'] == str(root_a)
    assert canonical_snapshot(c) == after and len(c.t.turns) == len(c.t.probes) == 1


def test_c16_second_page_workspace_selected_from_complete_canonical_directory(quick_cli, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import connect
    c = quick_cli
    for index in range(104):
        seed_workspace(c, 'qc23-page-' + str(index).zfill(3), 'Directory project ' + str(index))
    target = 'zz-qc23-target'
    seed_workspace(c, target, 'Only On Second Page')
    before = canonical_snapshot(c)
    pages = []
    original = c.t.call
    def observe(method, path, body=None):
        value = original(method, path, body)
        if method == 'GET' and urlsplit(path).path.endswith('/connections/workspaces'):
            pages.append((parse_qs(urlsplit(path).query), value))
        return value  # no authoritative DTO changes
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: observe)
    forbid_input(monkeypatch)
    review = invoke(c, capsys, ['connect', 'codex', 'Only On Second Page', '--workspace-id', target,
        '--profile', 'page-two', '--plan', '--json'])
    assert review['request']['workspace_id'] == target
    assert review['selection']['workspace_id'] == target
    assert review['selection']['project'] == str(c.project)
    assert len(pages) == 4  # initial catalog and final revision revalidation
    for offset in (0, 2):
        query1, first = pages[offset]
        query2, second = pages[offset + 1]
        assert query1 == {'limit': ['100']}
        assert query2 == {'limit': ['100'], 'cursor': [first['next_cursor']]}
        assert first['has_more'] is True and len(first['items']) == 100
        assert second['has_more'] is False and second['next_cursor'] is None
        assert target not in {row['workspace_id'] for row in first['items']}
        assert target in {row['workspace_id'] for row in second['items']}
        assert first['revision'] == second['revision'] == pages[0][1]['revision']
        assert first['total'] == second['total'] == len(before['workspaces']) > 100
        assert first['total_is_exact'] is second['total_is_exact'] is True
    assert canonical_snapshot(c) == before and c.t.turns == c.t.probes == []
''', encoding='utf-8')
src = (PRIOR / 'run.py').read_text()
start = src.index('nodes=[')
end = src.index('\nfor label,node in nodes:', start)
functions = ['test_c05_duplicate_names_require_explicit_selection_not_first',
    'test_c06_exact_workspace_disambiguates_duplicate_names',
    'test_c07_disagreeing_explicit_name_and_workspace_refuse_without_prompt',
    'test_c08_explicit_project_b_is_used_by_finish_while_cwd_remains_a',
    'test_c16_second_page_workspace_selected_from_complete_canonical_directory']
src = src[:start] + 'nodes=' + repr([(f.split('_')[1], 'tests/quick_connect/' + test.name + '::' + f) for f in functions]) + src[end:]
(HERE / 'run.py').write_text(src, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), external_test=str(test),
    sha256=hashlib.sha256(test.read_bytes()).hexdigest(), executed=False), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
