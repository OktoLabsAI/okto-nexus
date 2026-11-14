"""Offline synthetic fixtures only: no services, SQLite, provider or real gate."""
from pathlib import Path
from types import SimpleNamespace
import copy
import hashlib
import importlib
import importlib.util
import json
import sys

import pytest

import reconcile_presence as r

sys.path.insert(0, str(r.DRIVER_ROOT))
common = importlib.import_module('driver_common')
final = importlib.import_module('confirm_final_presence')
close = importlib.import_module('close_campaign')
spec = importlib.util.spec_from_file_location('fixture_collector',
    'C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/draft/controller/token_collector.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
DEPS = SimpleNamespace(common=common, final=final, close=close, collector=collector)


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def seal(value):
    value = {k: v for k, v in value.items() if k != 'state_sha256'}
    value['state_sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value


def repin(fixture):
    context, reference, ledger = fixture
    reference['retained_files'] = {str(p): r.digest(p) for p in [
        *(context.ROOT / 'public' / name for name in r.PUBLIC_NAMES), context.ROOT / 'private/controller.json',
        *(ledger / (name + suffix) for name in r.HISTORY for suffix in ('.reserved.json', '.returned.json'))]}


@pytest.fixture
def fixture(tmp_path):
    root, ledger = tmp_path / 'campaign', tmp_path / 'ledger'
    root.mkdir(); ledger.mkdir()
    paths = {k: str(root / n) for k, n in [('server_home', 'nexus-home'), ('operator_home', 'operator-home'),
        ('connector_state', 'connector-state'), ('private_evidence', 'private'), ('public_evidence', 'public')]}
    for p in paths.values():
        Path(p).mkdir()
    policy = {'carry_in_admissions': 6, 'carry_in_tokens': 89473, 'max_new_admissions': 5}
    context = SimpleNamespace(ROOT=root, args=SimpleNamespace(expected_proposal_sha256=r.PROPOSAL_SHA,
        approval_sha256=r.APPROVAL_SHA), P={'paths': paths, 'controller_preparation': {'policy': policy, 'ancestry': {}}},
        C={'tasks': {'nexus': {'name': 'NX', 'instance_id': 'NX-ID'}, 'connector': {'name': 'CN', 'instance_id': 'CN-ID'}}})
    for n in r.PUBLIC_NAMES:
        put(root / 'public' / n, {})
    for n in r.PRIVATE_NAMES:
        (root / 'private' / n).write_text('fixture')
    for name, (mode, selection, code) in r.HISTORY.items():
        value = {**common.tags(context), 'mode': mode, 'selection': selection}
        put(ledger / (name + '.reserved.json'), value)
        put(ledger / (name + '.returned.json'), {**value, 'returncode': code, 'wrapper_exit_confirmed': True})
    checkpoint = {'format': 11, 'root': str(root), 'proposal_sha256': r.PROPOSAL_SHA,
        'authorization_sha256': r.APPROVAL_SHA, 'policy': policy, 'ancestry': {},
        'owners': {'local': paths['server_home']}, 'faults': ['OBSERVATION_UNKNOWN', 'DEADLINE120'],
        'requests': {'m1v11-local-setup': {'kind': 'setup', 'lane': 'local', 'settled': False,
            'monitor': {'home': paths['server_home'], 'high_water': 0}}},
        'collector': collector.checkpoint(collector.initial_state())}
    put(root / 'private/controller.json', seal(checkpoint))
    put(root / 'public/local-setup-result.json', {'cli_exit': 3, 'reported_state': 'unconfirmed',
                                               'reported_code': 'INSTALLATION_UNCONFIRMED'})
    cleanup = {**common.tags(context), 'kind': 'PHYSICAL_OWNER_EXIT', 'task_name': 'NX',
        'task_stopped_confirmed': True, 'force_used': False, 'owned_pid_birth_exit_confirmed': True}
    put(root / 'public/cleanup-nexus.json', cleanup)
    cleanup_sha = r.digest(root / 'public/cleanup-nexus.json')
    put(root / 'public/lifecycle-nexus-uninstall-result.json', {'component': 'nexus', 'action': 'uninstall',
        'task_name': 'NX', 'returncode': 0, 'cleanup_proof_sha256': cleanup_sha})
    put(root / 'public/lifecycle-nexus-uninstall.json', {'cleanup_proof_sha256': cleanup_sha})
    reference = {'proposal_sha256': r.PROPOSAL_SHA, 'approval_sha256': r.APPROVAL_SHA,
        'public_names': sorted(r.PUBLIC_NAMES), 'private_names': sorted(r.PRIVATE_NAMES),
        'original_refusal_evidence': {'path': str(root / 'public/final-presence-original-refusal.json'), 'sha256': 'fixture'}}
    value = context, reference, ledger
    repin(value)
    return value


def fake_absence(context, component):
    return {'state': 'stopped', 'reason': 'NO_SERVICE_OWNER',
            'instance_id': context.C['tasks'][component]['instance_id'], 'pid': None, 'generation': None}


def observe(fixture, **overrides):
    context, reference, ledger = fixture
    kwargs = {'task_reader': lambda name: None, 'absence': fake_absence, 'port_probe': lambda *a: 57589,
              'connector_observer': lambda c: {**fake_absence(c, 'connector'), 'generation': '', 'running': False, 'ipc_ok': False}}
    kwargs.update(overrides)
    return r.observe(context, reference, DEPS, ledger, **kwargs)


def test_local_only_observation_and_neutral_closure(fixture):
    context, reference, ledger = fixture
    before = r.digest(context.ROOT / 'private/controller.json')
    result = observe(fixture)
    assert result['status'] == r.STATUS and result['original_helper_passed'] is False
    assert result['summary']['unsettled_requests'] == 1
    assert result['summary']['new_observed_tokens'] == 0
    common.public_save(context, r.PRESENCE, {**result, 'helper_sha256': 'helper', 'reference_sha256': 'reference'})
    closed = r.closure(context, reference, DEPS, ledger, helper_sha='helper', reference_sha='reference')
    assert closed['status'] == 'CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED'
    assert closed['cumulative_reserved_admissions'] == 7 and closed['cumulative_minimum_observed_tokens'] == 89473
    assert closed['faults_preserved'] == ['OBSERVATION_UNKNOWN', 'DEADLINE120']
    assert closed['billing_final'] is False and closed['acceptance_promoted'] is False
    assert before == r.digest(context.ROOT / 'private/controller.json')
    assert not (context.ROOT / 'public/final-presence.json').exists()


@pytest.mark.parametrize('mode,selection', [('lifecycle', ['connector', 'install']), ('plan', ['remote_plan']),
    ('plan', ['connector_host_draft']), ('remote_setup', ['transfer']), ('work', ['local', 'useful']),
    ('operator_bootstrap', ['once'])])
def test_any_additional_selection_refused(fixture, mode, selection):
    context, reference, ledger = fixture
    put(ledger / ('-'.join([mode, *selection]) + '.reserved.json'), {**common.tags(context), 'mode': mode, 'selection': selection})
    with pytest.raises(ValueError, match='EXACT_LOCAL_HISTORY_REQUIRED'):
        observe(fixture)


def test_missing_return_refused(fixture):
    (fixture[2] / 'setup-local.returned.json').unlink()
    with pytest.raises((OSError, ValueError)):
        observe(fixture)


def test_unconfirmed_return_refused_even_repinned(fixture):
    path = fixture[2] / 'setup-local.returned.json'
    value = r.read(path); value['wrapper_exit_confirmed'] = False; put(path, value); repin(fixture)
    with pytest.raises(common.Refused, match='WRAPPER_EXIT_UNCONFIRMED'):
        observe(fixture)


@pytest.mark.parametrize('area,name', [('public', 'remote-pty-reservation.json'), ('public', 'lifecycle-connector-install.json'),
    ('private', 'remote-setup.stdout'), ('connector-state', 'owner.json'), ('operator-home', 'profile.json')])
def test_remote_artifact_refused(fixture, area, name):
    put(fixture[0].ROOT / area / name, {})
    with pytest.raises(ValueError):
        observe(fixture)


@pytest.mark.parametrize('mutation', ['seal', 'owner', 'request', 'fault', 'settled'])
def test_checkpoint_guard(fixture, mutation):
    path = fixture[0].ROOT / 'private/controller.json'
    value = r.read(path)
    if mutation == 'seal':
        value['state_sha256'] = 'wrong'
    elif mutation == 'owner':
        value['owners']['connector'] = 'unexpected'
    elif mutation == 'request':
        value['requests']['m1v11-local-setup']['lane'] = 'connector'
    elif mutation == 'fault':
        value['faults'] = []
    else:
        value['requests']['m1v11-local-setup']['settled'] = True
    if mutation != 'seal':
        value = seal(value)
    put(path, value); repin(fixture)
    with pytest.raises((ValueError, common.Refused)):
        observe(fixture)


@pytest.mark.parametrize('component', ['nexus', 'connector'])
def test_existing_task_refused(fixture, component):
    name = fixture[0].C['tasks'][component]['name']
    with pytest.raises((ValueError, common.Refused)):
        observe(fixture, task_reader=lambda n: object() if n == name else None)


def test_nexus_physical_exit_required(fixture):
    path = fixture[0].ROOT / 'public/cleanup-nexus.json'
    value = r.read(path); value['owned_pid_birth_exit_confirmed'] = False; put(path, value); repin(fixture)
    with pytest.raises(common.Refused, match='PHYSICAL_CLEANUP_REQUIRED'):
        observe(fixture)


def test_port_failure_publishes_nothing(fixture):
    def busy(*args):
        raise OSError('fixture busy')
    with pytest.raises(OSError):
        observe(fixture, port_probe=busy)
    assert not (fixture[0].ROOT / 'public' / r.PRESENCE).exists()


def test_change_during_observation_refused(fixture):
    def changed(*args):
        put(fixture[0].ROOT / 'public/local-setup-result.json', {})
        return 57589
    with pytest.raises(ValueError, match='RETAINED_EVIDENCE_CHANGED'):
        observe(fixture, port_probe=changed)


def test_original_helper_failure_not_relabelled(fixture):
    context, _, ledger = fixture
    with pytest.raises(common.Refused, match='POSSIBLE_UNSELECTED_START'):
        final.check_component(context, 'connector', task_reader=lambda n: None,
                              inventory=common.invocation_inventory(context, ledger), absence=fake_absence)
    assert observe(fixture)['original_helper_passed'] is False


def test_closure_rejects_wrong_evidence_kind(fixture):
    context, reference, ledger = fixture
    result = observe(fixture)
    result.update(status='NORMAL_CLEANUP_CONFIRMED', helper_sha256='helper', reference_sha256='reference')
    common.public_save(context, r.PRESENCE, result)
    with pytest.raises(ValueError, match='SUPPLEMENTAL_PRESENCE_REQUIRED'):
        r.closure(context, reference, DEPS, ledger, helper_sha='helper', reference_sha='reference')


def test_exclusive_publication_does_not_replace_original(fixture):
    context = fixture[0]
    result = observe(fixture)
    path = common.public_save(context, r.PRESENCE, result)
    before = r.digest(path)
    with pytest.raises(FileExistsError):
        common.public_save(context, r.PRESENCE, {'replaced': True})
    assert r.digest(path) == before


def test_installed_connector_dataclass_no_owner_contract(fixture):
    # Import the actual installed campaign package; constructing this value is
    # pure and does not invoke _process_status, Scheduler, IPC or subprocesses.
    site = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/draft/installation/venv/Lib/site-packages')
    sys.path.insert(0, str(site))
    from okto_nexus_connector.daemon import manager
    assert Path(manager.__file__).resolve() == (site / 'okto_nexus_connector/daemon/manager.py').resolve()
    value = manager.DaemonStatus(False, None, '', '', '', '', None, False,
        state='stopped', reason='NO_SERVICE_OWNER',
        instance_id=fixture[0].C['tasks']['connector']['instance_id']).to_json()
    assert value['generation'] == ''
    result = observe(fixture, connector_observer=lambda c: value)
    assert result['tasks']['connector']['canonical_absence']['generation'] == ''


@pytest.mark.parametrize('field,value', [('generation', 'active-generation'), ('generation', None),
    ('generation', False), ('generation', 0), ('state', 'unknown'), ('state', 'starting'),
    ('reason', 'INSTANCE_OWNERSHIP_UNCONFIRMED'), ('pid', 44584), ('running', True),
    ('ipc_ok', True), ('instance_id', 'another-owner')])
def test_connector_canonical_absence_is_exact(fixture, field, value):
    raw = {**fake_absence(fixture[0], 'connector'), 'generation': '', 'running': False, 'ipc_ok': False}
    raw[field] = value
    with pytest.raises(ValueError, match='CONNECTOR_CANONICAL_OWNER_ABSENCE_UNCONFIRMED'):
        observe(fixture, connector_observer=lambda c: raw)
