"""Composed project/CWD CLI cases; canonical SQLite/HTTP, inert peers."""
from pathlib import Path
import json
from types import SimpleNamespace

import pytest
from test_quick_connect_cli import (  # noqa: F401
    checking, first_connection, invoke, isolated_provider_environment, local_setup,
    quick_cli, terminal,
)
from test_quick_connect_extra_scenarios import canonical_snapshot


def create_project(c, capsys, name, profile):
    base = ['connect', 'codex', name, '--profile', profile, '--json']
    review = invoke(c, capsys, [*base, '--plan'])
    return invoke(c, capsys, [*base, '--approve', review['review_revision']])


def two_projects(c, capsys, monkeypatch):
    root_a = c.project
    first = create_project(c, capsys, 'Project A', 'project-a')
    root_b = root_a.parent / 'physical-project-b'
    root_b.mkdir()
    monkeypatch.chdir(root_b)
    c.project = root_b
    second = create_project(c, capsys, 'Project B', 'project-b')
    assert first['workspace_id'] != second['workspace_id']
    monkeypatch.chdir(root_a)
    c.project = root_a
    return root_a, root_b, first, second


def forbid_input(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda *a, **k: pytest.fail('JSON read interactive input'))


def test_c01_mapped_cwd_bare_and_harness_resume_exact_reference(quick_cli, capsys, monkeypatch):
    c = quick_cli
    _, _, first = first_connection(c, capsys, name='Mapped Logical Project')
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    forbid_input(monkeypatch)
    for tokens in (['connect', '--json'], ['connect', 'codex', '--json']):
        from okto_nexus.adapters.inbound.cli import main
        # Both commands are literal public grammar, without the fixture's
        # additional explicit legacy provider-home selector.
        code = main.main([*tokens, '--home', str(c.home)])
        captured = capsys.readouterr()
        assert code == 0, captured.out + captured.err
        result = json.loads(captured.out)
        assert result['quick_connect']['canonical_reference'] == first['quick_connect']['canonical_reference']
        assert result['quick_connect']['project_name'] == 'Mapped Logical Project'
        assert result['quick_connect']['project_root'] == str(c.project)
        assert result['binding_id'] == first['binding_id']
        assert result['session_state'] == 'not_checked' and result['work_state'] == 'not_submitted'
        assert canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes


def test_c03_c04_concordant_and_new_logical_labels_never_become_paths(quick_cli, capsys, monkeypatch):
    c = quick_cli
    _, _, first = first_connection(c, capsys, name='Human Logical A')
    root_a = c.project
    before = canonical_snapshot(c)
    result = invoke(c, capsys, ['connect', 'codex', 'Human Logical A', '--json'])
    assert result['quick_connect']['canonical_reference'] == first['quick_connect']['canonical_reference']
    assert result['quick_connect']['project_root'] == str(root_a)
    assert not (root_a / 'Human Logical A').exists()
    assert canonical_snapshot(c) == before
    physical = root_a.parent / 'new-physical-folder'
    physical.mkdir()
    monkeypatch.chdir(physical)
    c.project = physical
    review = invoke(c, capsys, ['connect', 'codex', 'A Completely Logical Label', '--profile', 'new-label', '--plan', '--json'])
    assert review['selection']['project'] == str(physical)
    assert review['selection']['label'] == 'A Completely Logical Label'
    assert review['quick_connect']['project_root'] == str(physical)
    assert Path.cwd() == physical and not (physical / 'A Completely Logical Label').exists()
    assert canonical_snapshot(c) == before


def test_c09_other_mapped_project_root_requires_explicit_tty_choice(quick_cli, capsys, monkeypatch):
    from okto_nexus.adapters.inbound.cli import connect
    c = quick_cli
    root_a, root_b, _, second = two_projects(c, capsys, monkeypatch)
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def answer(prompt):
        prompts.append(prompt)
        if prompt == 'Use approved folder: ':
            return '1'
        if prompt == 'Choice: ':
            return 'r'
        if prompt == 'Confirm resume? [y/N] ':
            return 'y'
        pytest.fail('Unexpected prompt: ' + prompt)
    monkeypatch.setattr('builtins.input', answer)
    displayed = []
    original = connect._display
    def observe(value, json_mode):
        displayed.append(value)
        return original(value, json_mode)
    monkeypatch.setattr(connect, '_display', observe)
    assert c.run(['connect', 'codex', 'Project B', '--plan', '--no-chat']) == 0
    capsys.readouterr()
    assert prompts == ['Use approved folder: ', 'Choice: ']
    result = displayed[-1]
    assert result['quick_connect']['status'] == 'planned'
    assert 'canonical_reference' not in result['quick_connect']
    shortcuts = list((c.home / 'terminal/profiles').glob('canonical-*.json'))
    assert len(shortcuts) == 1
    shortcut = json.loads(shortcuts[0].read_text())
    assert shortcut['selection']['project'] == str(root_b)
    assert shortcut['selection']['binding_id'] == second['binding_id']
    assert shortcut['selection']['workspace_id'] == second['workspace_id']
    assert canonical_snapshot(c) == before
    # Explicit observation after plan, same selection; no execution permission
    # or Test is inferred from the planned envelope.
    assert c.run(['connect', 'codex', 'Project B', '--no-chat']) == 0
    capsys.readouterr()
    assert prompts == ['Use approved folder: ', 'Choice: '] * 2 + ['Confirm resume? [y/N] ']
    result = displayed[-1]
    assert result['quick_connect']['canonical_reference'] == second['quick_connect']['canonical_reference']
    assert result['quick_connect']['project_root'] == str(root_b)
    assert result['quick_connect']['project_name'] == 'Project B'
    assert Path.cwd() == root_a  # choosing execution root does not chdir the caller
    assert canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes


def test_c10_explicit_project_root_is_not_replaced_by_other_label(quick_cli, capsys, monkeypatch):
    c = quick_cli
    root_a, _, _, _ = two_projects(c, capsys, monkeypatch)
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    forbid_input(monkeypatch)
    value = invoke(c, capsys, ['connect', 'codex', 'Project B', '--project', str(root_a), '--plan', '--json'], expected=3)
    assert value['code'] == 'PROJECT_DIRECTORY_MISMATCH'
    assert Path.cwd() == root_a and canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes


def test_c11_json_root_label_ambiguity_refuses_without_input_or_chdir(quick_cli, capsys, monkeypatch):
    c = quick_cli
    root_a, _, _, _ = two_projects(c, capsys, monkeypatch)
    before = canonical_snapshot(c)
    turns, probes = tuple(c.t.turns), tuple(c.t.probes)
    forbid_input(monkeypatch)
    value = invoke(c, capsys, ['connect', 'codex', 'Project B', '--plan', '--json'], expected=3)
    assert value['code'] == 'PROJECT_DIRECTORY_MISMATCH'
    assert Path.cwd() == root_a and canonical_snapshot(c) == before
    assert tuple(c.t.turns) == turns and tuple(c.t.probes) == probes


def test_c17_cancel_and_approval_never_mkdir_the_logical_label(quick_cli, capsys, monkeypatch):
    from okto_nexus.adapters.inbound.cli import connect
    c = quick_cli
    label = 'Only Nexus Logical Project'
    before = canonical_snapshot(c)
    initial_children = set(c.project.iterdir())
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def cancel(prompt):
        prompts.append(prompt)
        assert 'Confirm this review' in prompt
        return 'cancel'
    monkeypatch.setattr('builtins.input', cancel)
    assert c.run(['connect', 'codex', label, '--profile', 'canceled', '--no-chat']) == 0
    capsys.readouterr()
    assert len(prompts) == 1 and canonical_snapshot(c) == before
    assert c.t.turns == c.t.probes == []
    assert set(c.project.iterdir()) == initial_children and not (c.project / label).exists()
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    result = create_project(c, capsys, label, 'approved-new-intent')
    assert result['quick_connect']['project_name'] == label
    assert result['quick_connect']['project_root'] == str(c.project)
    assert set(c.project.iterdir()) == initial_children and not (c.project / label).exists()
    after = canonical_snapshot(c)
    assert len(after['workspaces']) == len(before['workspaces']) + 1
    assert len(after['execution_bindings']) == len(before['execution_bindings']) + 1
    assert len(c.t.turns) == len(c.t.probes) == 1
