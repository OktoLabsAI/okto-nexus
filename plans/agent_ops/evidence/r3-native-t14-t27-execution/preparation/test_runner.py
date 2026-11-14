"""Offline only: no service/task/runtime/provider operations."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('finite_native_runner', ROOT / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
PLAN = json.loads((ROOT / 'plan.json').read_bytes())


def test_command_scope_and_caller_context():
    assert sum(map(len, PLAN['commands'].values())) == 12
    assert PLAN['environments']['A']['PATH'] != PLAN['environments']['B']['PATH']
    assert PLAN['project_a'] != PLAN['caller_b']
    for name, commands in PLAN['commands'].items():
        assert set(commands) == {'install-A', 'start-B', 'stop-installed', 'uninstall', 'foreground', 'stop-foreground'}
        for phase, step in commands.items():
            assert step['argv'][:4] == [sys.executable, '-I', '-B', '-m']
            assert not {'--force', 'login', 'send', 'setup', 'restart'} & set(step['argv'])
            assert step['environment'] == ('A' if phase == 'install-A' else 'B')
            assert step['cwd'] == (PLAN['project_a'] if phase == 'install-A' else PLAN['caller_b'])
    assert '--project-root' not in PLAN['commands']['nexus']['start-B']['argv']
    assert '--port' not in PLAN['commands']['nexus']['start-B']['argv']


def test_connector_installed_parser_accepts_all_exact_commands():
    from okto_nexus_connector.cli.main import build_parser
    for step in PLAN['commands']['connector'].values():
        args = build_parser().parse_args(step['argv'][5:])
        assert args.state_dir == Path(PLAN['homes']['connector'])
        assert args.json and args.non_interactive
        assert not getattr(args, 'force', False)


def test_nexus_foreground_config_is_explicit_and_offline():
    from okto_nexus.adapters.inbound.cli.serve import _split_serve_args
    from okto_nexus.config import load_config
    port, host, project, _, rest = _split_serve_args(PLAN['commands']['nexus']['foreground']['argv'][6:], PLAN['environments']['B'])
    config = load_config(PLAN['environments']['B'], rest)
    assert (port, host, project) == (PLAN['port'], '127.0.0.1', PLAN['project_a'])
    assert str(config.home_dir) == PLAN['homes']['nexus']
    assert config.embedding_mode == 'off' and config.feature_harness_integrations is False


def test_exact_integration_exclusions_match_installed_contract():
    from okto_nexus.adapters.outbound.service_manager.installation import INSTALLATION_NAME, CONTROL_NAME
    from okto_nexus_connector.platform.service_context import INSTALLATION, CONTROL
    assert PLAN['uninstall_removes']['nexus'] == [INSTALLATION_NAME, CONTROL_NAME, 'nexus.db.service-installation.json']
    assert PLAN['uninstall_removes']['connector'] == [INSTALLATION, CONTROL]


@pytest.mark.parametrize('mutation', ['none', 'changed', 'deleted', 'added'])
def test_uninstall_fingerprint_preserves_every_nonreceipt_file(tmp_path, mutation):
    data = tmp_path / 'nexus.db'
    data.write_bytes(b'fixture runtime data')
    receipt = tmp_path / 'service-installation.json'
    receipt.write_text('private fixture receipt')
    before = runner.fingerprint(tmp_path, ['service-installation.json'])
    receipt.unlink()
    if mutation == 'changed': data.write_bytes(b'different runtime data')
    elif mutation == 'deleted':
        data.unlink(); (tmp_path / 'other-data').write_bytes(b'remaining')
    elif mutation == 'added': (tmp_path / 'new-data').write_bytes(b'new')
    after = runner.fingerprint(tmp_path, ['service-installation.json'])
    if mutation == 'none': runner.validate_preservation(before, after)
    else:
        with pytest.raises(ValueError, match='UNINSTALL_CHANGED_RETAINED_DATA'):
            runner.validate_preservation(before, after)


def test_empty_runtime_data_refused(tmp_path):
    with pytest.raises(ValueError, match='NO_RUNTIME_DATA'):
        runner.fingerprint(tmp_path, [])


@pytest.mark.parametrize('name', ['nexus', 'connector'])
@pytest.mark.parametrize('drift', ['none', 'path', 'cwd', 'executable', 'native-cwd', 'project-or-root'])
def test_native_context_requires_original_configuration(tmp_path, name, drift):
    plan = copy.deepcopy(PLAN)
    plan['homes'][name] = str(tmp_path)
    cwd = plan['project_a'] if name == 'nexus' else str(tmp_path)
    context = {'executable': plan['python'], 'cwd': cwd, 'root': str(tmp_path),
        'environment': {'PATH': os.pathsep.join(dict.fromkeys(str(Path(p).resolve()) for p in plan['environments']['A']['PATH'].split(os.pathsep))),
                        'OKTO_NEXUS_CONNECTOR_STATE': str(tmp_path)},
        'arguments': ['--project-root', plan['project_a'], '--port', str(plan['port']), '--embedding-mode', 'off', '--feature-harness-integrations', 'false']}
    native_cwd = cwd
    if drift == 'path': context['environment']['PATH'] = plan['environments']['B']['PATH']
    elif drift == 'cwd': context['cwd'] = plan['caller_b']
    elif drift == 'executable': context['executable'] = str(tmp_path / 'other.exe')
    elif drift == 'native-cwd': native_cwd = plan['caller_b']
    elif drift == 'project-or-root':
        if name == 'nexus': context['arguments'][1] = plan['caller_b']
        else: context['root'] = plan['caller_b']
    (tmp_path / 'service-context.json').write_text(json.dumps(context), encoding='utf-8')
    command = str(Path(plan['python']).with_name('pythonw.exe'))
    xml = '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Actions><Exec><Command>' + escape(command) + '</Command><WorkingDirectory>' + escape(native_cwd) + '</WorkingDirectory></Exec></Actions></Task>'
    task = SimpleNamespace(active=True, enabled=True, xml=xml, digest='fixture')
    service = SimpleNamespace(name='fixture-task', observe=lambda: ({}, task))
    if drift == 'none':
        result = runner.native_context(plan, name, service)
        assert result['recorded_path_matches_A_not_caller_B']
        assert ('no project binding' in result['project_scope']) == (name == 'connector')
    else:
        with pytest.raises(ValueError): runner.native_context(plan, name, service)


def test_isolated_entrypoint_help_has_no_runtime_effects():
    result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(ROOT / 'run.py'), '--help'],
                            capture_output=True, timeout=30)
    assert result.returncode == 0
    assert b'expected-plan-sha256' in result.stdout
    assert not (ROOT / 'public').exists() and not (ROOT / 'private').exists()
