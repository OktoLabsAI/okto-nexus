"""Passive status survives expired discovery roots without weakening startup."""
import json
import sys
from unittest.mock import Mock

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus.bootstrap.local_discovery import split_discovery_args
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def selected(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    missing = tmp_path / 'removed' / 'native'
    path = home / 'service-context.json'
    atomic_json(path, {'revision': 1, 'component': 'server',
        'executable': sys.executable, 'environment_prefix': sys.prefix,
        'cwd': str(tmp_path), 'arguments': ['--home', str(home),
            '--embedding-mode', 'off', '--harness-root', str(missing)], 'environment': {}})
    # No owner receipt, installation or database exists: the real canonical
    # inspector must establish absence without transport or process launch.
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', Mock(side_effect=AssertionError('No child allowed')))
    return home, missing, path


@pytest.mark.parametrize('explicit', [False, True])
def test_status_inspects_absence_with_missing_saved_or_explicit_root(selected, explicit, capsys):
    home, missing, path = selected
    if explicit:
        value = json.loads(path.read_text())
        value['arguments'] = value['arguments'][:-2]
        atomic_json(path, value)
    before = path.read_bytes()
    args = ['status', '--home', str(home), '--json']
    if explicit:
        args += ['--harness-root', str(missing)]
    assert run_service(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'stopped' and result['reason'] == 'NO_SERVICE_OWNER'
    assert result['instance_id'] == server_instance_id(home, home / 'nexus.db')
    assert path.read_bytes() == before
    assert not missing.exists() and not (home / 'nexus.db').exists()


@pytest.mark.parametrize('action', ['start', 'stop', 'restart'])
def test_nonstatus_routes_keep_strict_saved_discovery(selected, action, capsys):
    home, missing, path = selected
    before = path.read_bytes()
    assert run_service([action, '--home', str(home), '--json']) == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'CONFIG_ERROR'
    assert path.read_bytes() == before and not missing.exists()


@pytest.mark.parametrize('saved', [False, True])
def test_status_rejects_relative_discovery(selected, saved, capsys):
    home, _, path = selected
    args = ['status', '--home', str(home), '--json']
    if saved:
        value = json.loads(path.read_text())
        value['arguments'][-1] = 'relative-root'
        atomic_json(path, value)
    else:
        args += ['--harness-root', 'relative-root']
    before = path.read_bytes()
    assert run_service(args) == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'CONFIG_ERROR'
    assert path.read_bytes() == before


@pytest.mark.parametrize('arguments', [
    ['--harness-root'], ['--harness-root='], ['--pi-node', 'relative'],
])
def test_passive_parser_preserves_invalid_shape_refusal(arguments):
    with pytest.raises(OktoNexusError):
        split_discovery_args(arguments, require_paths=False)


def test_parser_remains_strict_by_default(tmp_path):
    with pytest.raises(OktoNexusError):
        split_discovery_args(['--harness-root', str(tmp_path / 'absent')])
