"""Synthetic filesystem/process fixtures only; no live service or campaign calls."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib
import importlib.util
import json
import sys

import pytest
import supplement_common as s
import stop_once as stop
import reconcile_final as final

sys.path.insert(0, str(s.DRIVERS))
common = importlib.import_module('driver_common')
presence = importlib.import_module('confirm_final_presence')
observation = importlib.import_module('m1_v12_observation')
closure = importlib.import_module('close_campaign')
COLLECTOR = s.BUNDLE / 'draft/controller/token_collector.py'
spec = importlib.util.spec_from_file_location('fixture_collector', COLLECTOR)
collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)
DEPS = SimpleNamespace(common=common, presence=presence, observation=observation, closure=closure)


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def seal(value):
    value = {k: v for k, v in value.items() if k != 'state_sha256'}
    value['state_sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root, output, drivers = tmp_path / 'campaign', tmp_path / 'supplement-output', tmp_path / 'drivers'
    for p in (root, output, drivers / 'runtime-private'):
        p.mkdir(parents=True)
    paths = {k: str(root / n) for k, n in [('server_home', 'server'), ('operator_home', 'operator'),
        ('connector_state', 'connector'), ('public_evidence', 'public'), ('private_evidence', 'private')]}
    for value in paths.values():
        Path(value).mkdir()
    profile = Path(paths['server_home']) / 'terminal/profiles/m1v12-local.json'
    profile.parent.mkdir(parents=True)
    put(profile, {'synthetic_profile_only': True})
    policy = {'revision': 12, 'carry_in_admissions': 7, 'carry_in_tokens': 89473,
              'max_new_admissions': 5, 'max_cumulative_admissions': 12}
    c = SimpleNamespace(ROOT=root, args=SimpleNamespace(expected_proposal_sha256=s.PROPOSAL_SHA, approval_sha256=s.APPROVAL_SHA),
        P={'paths': paths, 'package_pins': {'python': 'FIXTURE_NO_EXECUTION'},
           'controller_preparation': {'policy': policy, 'ancestry': {}},
           'execution_bundle': {'files': {'controller_token_collector': {'path': str(COLLECTOR), 'sha256': s.sha(COLLECTOR)}}}},
        C={'tasks': {name: {'name': 'TASK-' + name, 'instance_id': 'INSTANCE-' + name} for name in ('nexus', 'connector')},
           'steps': [{'component': 'nexus', 'action': 'stop', 'task_name': 'TASK-nexus',
                      'argv': ['FIXTURE_NO_EXECUTION', 'service', 'stop', '--json']}]}, env=lambda: {'FIXTURE': '1'})
    raw = {'state': 'degraded', 'reason': 'SERVICE_UNREACHABLE',
           'next_action': 'Inspect startup/transport diagnostics for this instance; no process was started.'}
    put(root / 'private/nexus-stop.stdout', raw)
    monkeypatch.setattr(s, 'OLD_STOP_SHA', s.sha(root / 'private/nexus-stop.stdout'))
    put(Path(paths['server_home']) / 'service-control.json', {'desired': 'running', 'generation': None, 'launch_requested': False})
    monkeypatch.setattr(s, 'CONTROL_SHA', s.sha(Path(paths['server_home']) / 'service-control.json'))
    value = {'format': 11, 'root': str(root), 'proposal_sha256': s.PROPOSAL_SHA, 'authorization_sha256': s.APPROVAL_SHA,
        'policy': policy, 'ancestry': {}, 'owners': {'local': paths['server_home']}, 'faults': ['DEADLINE120'],
        'requests': {'m1v12-local-setup': {'kind': 'setup', 'lane': 'local', 'settled': True,
            'monitor': {'high_water': 22178}}}, 'collector': collector.checkpoint(collector.initial_state()),
        'independent_observation': {'worker_in_flight': False}}
    put(root / 'private/controller.json', seal(value))
    monkeypatch.setattr(s, 'CHECKPOINT_SHA', s.sha(root / 'private/controller.json'))
    for name in final.PUBLIC_ALLOWED:
        put(root / 'public' / name, {})
    put(root / 'public/lifecycle-nexus-stop-result.json', {'output_sha256': s.OLD_STOP_SHA, 'returncode': 3, 'reported_state': 'degraded'})
    put(root / 'public/local-setup-result.json', {'cli_exit': 0, 'reported_state': 'configured'})
    put(root / 'public/local-setup-dispatch.json', {'request_id': 'm1v12-local-setup', 'reservation_persisted': True})
    for name in final.HISTORY:
        mode, *selection = name.split('-')
        record = {**common.tags(c), 'mode': mode, 'selection': selection}
        put(drivers / 'runtime-private' / (name + '.reserved.json'), record)
        put(drivers / 'runtime-private' / (name + '.returned.json'), {**record, 'wrapper_exit_confirmed': True, 'returncode': 0})
    monkeypatch.setattr(s, 'DRIVERS', drivers)
    cleanup = {**common.tags(c), 'kind': 'PHYSICAL_OWNER_EXIT', 'task_name': 'TASK-nexus',
               'task_stopped_confirmed': True, 'owned_pid_birth_exit_confirmed': True, 'force_used': False}
    put(root / 'public/cleanup-nexus.json', cleanup)
    cleanup_sha = s.sha(root / 'public/cleanup-nexus.json')
    put(root / 'public/lifecycle-nexus-uninstall.json', {'cleanup_proof_sha256': cleanup_sha})
    put(root / 'public/lifecycle-nexus-uninstall-result.json', {'component': 'nexus', 'action': 'uninstall',
        'task_name': 'TASK-nexus', 'returncode': 0, 'cleanup_proof_sha256': cleanup_sha})
    return c, output


class Handle:
    closed = False
    def birth(self): return s.BIRTH
    def wait(self, _): return False
    def close(self): self.closed = True


def owner(c, _component):
    return {'pid': s.PID, 'generation': s.GENERATION, 'instance_id': c.C['tasks']['nexus']['instance_id'],
            'task': {'name': 'TASK-nexus', 'digest': s.TASK_DIGEST}}


def run(fixture, **overrides):
    c, output = fixture
    handle = Handle()
    def spawn(argv, **kwargs):
        assert argv == c.C['steps'][0]['argv'] and '--force' not in argv
        assert (output / 'normal-stop.reserved.json').exists()
        kwargs['stdout'].write(json.dumps({'state': 'stopped', 'reason': 'SHUTDOWN_COMPLETE',
            'shutdown_outcome': 'drained', 'instance_id': c.C['tasks']['nexus']['instance_id']}).encode())
        kwargs['stdout'].flush()
        return SimpleNamespace(pid=777, wait=lambda: 0)
    options = {'observe': owner, 'process': lambda _: handle, 'popen': spawn}
    options.update(overrides)
    result = stop.run(c, DEPS, output, **options)
    assert handle.closed or 'process' in overrides
    return result


def absence(c, component):
    raw = {'state': 'stopped', 'reason': 'NO_SERVICE_OWNER', 'instance_id': c.C['tasks'][component]['instance_id'],
           'pid': None, 'generation': None if component == 'nexus' else '', 'running': False, 'ipc_ok': False}
    return observation.validate_canonical_absence(c, component, raw)


def test_once_then_snapshot_observe_close_preserves_configured_setup(fixture):
    c, output = fixture
    before = s.sha(c.ROOT / 'private/controller.json')
    assert run(fixture)['returncode'] == 0
    reference = {'inputs': final.local_inputs(c, DEPS, output)}
    result = final.observe(c, DEPS, output, reference, task_reader=lambda _: None,
                           absence=absence, port_probe=lambda *_: 58631)
    common.public_save(c, final.PRESENCE, {**result, 'proof_snapshot_sha256': 'proof', 'supplement_manifest_sha256': 'manifest'})
    result = final.close(c, DEPS, output, reference, 'proof', 'manifest')
    assert result['cumulative_reserved_admissions'] == 8 and result['cumulative_minimum_observed_tokens'] == 111651
    assert result['new_observed_tokens'] == 22178 and result['unsettled_requests'] == 0
    assert result['faults_preserved'] == ['DEADLINE120'] and result['acceptance_promoted'] is False
    assert result['configured_setup_retained'] is True and result['billing_final'] is False
    assert s.sha(c.ROOT / 'private/controller.json') == before
    with pytest.raises(FileExistsError):
        run(fixture, popen=lambda *_a, **_k: pytest.fail('replay'))


@pytest.mark.parametrize('field,value', [('pid', 1), ('generation', 'changed'), ('instance_id', 'foreign'), ('task', {'name': 'TASK-nexus', 'digest': 'other'})])
def test_wrong_owner_refused_before_reservation(fixture, field, value):
    def changed(c, component):
        return {**owner(c, component), field: value}
    with pytest.raises(ValueError, match='EXACT_LIVE_OWNER_REQUIRED'):
        run(fixture, observe=changed, popen=lambda *_a, **_k: pytest.fail('effect'))
    assert not (fixture[1] / 'normal-stop.reserved.json').exists()


@pytest.mark.parametrize('kind', ['birth', 'exited'])
def test_pid_reuse_or_exit_refused(fixture, kind):
    handle = Handle()
    if kind == 'birth': handle.birth = lambda: s.BIRTH + 1
    else: handle.wait = lambda _: True
    with pytest.raises(ValueError, match='EXACT_LIVE_OWNER_REQUIRED'):
        run(fixture, process=lambda _: handle, popen=lambda *_a, **_k: pytest.fail('effect'))
    assert handle.closed


def test_owner_changes_after_selection_no_post_and_reservation_retained(fixture):
    calls = []
    def changing(c, component):
        calls.append(1)
        return owner(c, component) if len(calls) == 1 else {**owner(c, component), 'generation': 'changed'}
    with pytest.raises(ValueError):
        run(fixture, observe=changing, popen=lambda *_a, **_k: pytest.fail('effect'))
    assert (fixture[1] / 'normal-stop.reserved.json').exists()
    assert not (fixture[1] / 'normal-stop.process.json').exists()


@pytest.mark.parametrize('file', ['private/nexus-stop.stdout', 'private/controller.json', 'server/service-control.json'])
def test_changed_retained_inputs_prevent_effect(fixture, file):
    (fixture[0].ROOT / file).write_text('{}')
    with pytest.raises(ValueError):
        run(fixture, popen=lambda *_a, **_k: pytest.fail('effect'))


def test_force_never_dispatches(fixture):
    fixture[0].C['steps'][0]['argv'].append('--force')
    with pytest.raises(ValueError, match='NORMAL_STOP_SCOPE_CHANGED'):
        run(fixture, popen=lambda *_a, **_k: pytest.fail('effect'))


def test_spawn_failure_is_reserved_not_replayed(fixture):
    def failed(*_a, **_k): raise OSError('fixture')
    with pytest.raises(OSError): run(fixture, popen=failed)
    assert (fixture[1] / 'normal-stop.reserved.json').exists()
    with pytest.raises(FileExistsError): run(fixture, popen=lambda *_a, **_k: pytest.fail('replay'))


def test_actual_cleanup_snapshot_cannot_be_created_early(fixture):
    run(fixture)
    (fixture[0].ROOT / 'public/lifecycle-nexus-uninstall-result.json').unlink()
    with pytest.raises(ValueError, match='LOCAL_PUBLIC_SET_CHANGED'):
        final.local_inputs(fixture[0], DEPS, fixture[1])


@pytest.mark.parametrize('mode,selection', [('operator_bootstrap', ['once']), ('remote_setup', ['transfer']),
    ('work', ['local', 'useful']), ('lifecycle', ['connector', 'install'])])
def test_final_rejects_any_nonlocal_selection(fixture, mode, selection):
    run(fixture)
    record = {**common.tags(fixture[0]), 'mode': mode, 'selection': selection}
    name = '-'.join([mode, *selection])
    put(s.DRIVERS / 'runtime-private' / (name + '.reserved.json'), record)
    put(s.DRIVERS / 'runtime-private' / (name + '.returned.json'), {**record, 'wrapper_exit_confirmed': True, 'returncode': 0})
    with pytest.raises(ValueError, match='EXACT_LOCAL_HISTORY_REQUIRED'):
        final.local_inputs(fixture[0], DEPS, fixture[1])


@pytest.mark.parametrize('kind', ['physical_exit', 'task', 'canonical', 'port', 'changed_snapshot'])
def test_final_presence_retains_all_original_cleanup_requirements(fixture, kind):
    c, output = fixture
    run(fixture)
    if kind == 'physical_exit':
        path = c.ROOT / 'public/cleanup-nexus.json'
        value = s.read(path); value['owned_pid_birth_exit_confirmed'] = False; put(path, value)
    reference = {'inputs': final.local_inputs(c, DEPS, output)}
    if kind == 'changed_snapshot': reference['inputs']['controller_checkpoint_sha256'] = 'wrong'
    def observed(ctx, component):
        if kind == 'canonical': raise common.Refused('CANONICAL_OWNER_ABSENCE_UNCONFIRMED')
        return absence(ctx, component)
    def port(*_):
        if kind == 'port': raise OSError('busy')
        return 58631
    with pytest.raises((ValueError, common.Refused, OSError)):
        final.observe(c, DEPS, output, reference, task_reader=lambda _: object() if kind == 'task' else None,
                      absence=observed, port_probe=port)
    assert not (c.ROOT / 'public' / final.PRESENCE).exists()


def test_changed_checkpoint_after_observation_refuses_close(fixture):
    c, output = fixture
    run(fixture)
    reference = {'inputs': final.local_inputs(c, DEPS, output)}
    value = final.observe(c, DEPS, output, reference, task_reader=lambda _: None, absence=absence, port_probe=lambda *_: 58631)
    common.public_save(c, final.PRESENCE, {**value, 'proof_snapshot_sha256': 'proof', 'supplement_manifest_sha256': 'manifest'})
    (c.ROOT / 'private/controller.json').write_text('{}')
    with pytest.raises(ValueError, match='CONTROLLER_CHANGED'):
        final.close(c, DEPS, output, reference, 'proof', 'manifest')


def test_wrong_proposal_refuses_before_import_or_effect():
    args = SimpleNamespace(expected_proposal_sha256='wrong')
    with pytest.raises(ValueError, match='ONE_PROPOSAL_REQUIRED'):
        s.load(args)


@pytest.mark.parametrize('raw', [b'not valid JSON', b'[]'])
def test_noncanonical_output_preserves_exit_receipt_without_cleanup_success(fixture, raw):
    def spawn(argv, **kwargs):
        kwargs['stdout'].write(raw); kwargs['stdout'].flush()
        return SimpleNamespace(pid=777, wait=lambda: 0)
    result = run(fixture, popen=spawn)
    assert result['returncode'] == 0 and result['wrapper_exit_confirmed'] is True
    assert result['reported']['state'] == 'unknown' and result['output_parse_error'] is not None
    assert result['physical_owner_exit_inferred'] is False
    assert s.read(fixture[1] / 'normal-stop.returned.json') == result
    with pytest.raises(ValueError, match='SUPPLEMENTAL_NORMAL_STOP_UNCONFIRMED'):
        final.local_inputs(fixture[0], DEPS, fixture[1])


def test_configured_profile_must_remain_present_and_unchanged(fixture):
    c, output = fixture
    run(fixture)
    reference = {'inputs': final.local_inputs(c, DEPS, output)}
    profile = Path(c.P['paths']['server_home']) / 'terminal/profiles/m1v12-local.json'
    profile.write_text('different fixture profile')
    with pytest.raises(ValueError, match='PROOF_SNAPSHOT_CHANGED'):
        final.observe(c, DEPS, output, reference, task_reader=lambda _: None, absence=absence, port_probe=lambda *_: 58631)
    profile.unlink()
    with pytest.raises(ValueError, match='CONFIGURED_PROFILE_NOT_RETAINED'):
        final.local_inputs(c, DEPS, output)


def test_data_retention_is_positive_not_assumed(fixture):
    c, output = fixture
    run(fixture)
    Path(c.P['paths']['connector_state']).rmdir()
    with pytest.raises(ValueError, match='CAMPAIGN_DIRECTORIES_NOT_RETAINED'):
        final.local_inputs(c, DEPS, output)


@pytest.mark.parametrize('script', ['stop_once.py', 'reconcile_final.py'])
def test_isolated_entrypoint_imports_before_gate_without_effect(script):
    import subprocess
    result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).parent / script), '--help'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert '--manifest-sha256' in result.stdout
