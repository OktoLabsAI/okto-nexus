"""Pure v12 fixtures; actual installed dataclass construction has no process I/O."""
from pathlib import Path
import importlib.util
import json
import sys

import pytest
import driver_common as common
import confirm_final_presence as presence
import m1_v12_observation as observation
import close_campaign as closure
from test_drivers import context, seal, absent

COLLECTOR = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/draft/controller/token_collector.py')
spec = importlib.util.spec_from_file_location('test_presence_collector', COLLECTOR)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def local_only(context, tmp_path, monkeypatch):
    c = context
    directory = tmp_path / 'driver/runtime-private'
    directory.mkdir(parents=True)
    monkeypatch.setattr(common, 'HERE', directory.parent)
    (c.ROOT / 'operator').mkdir()
    c.P['paths'].update(server_home=str(c.ROOT / 'server'), connector_state=str(c.ROOT / 'connector'),
                        operator_home=str(c.ROOT / 'operator'))
    c.P['request_ids'] = {'productive_setup': ['m1v12-local-setup']}
    c.P['execution_bundle']['files']['controller_token_collector'] = {'path': str(COLLECTOR), 'sha256': common.sha(COLLECTOR)}
    choices = [('lifecycle', ['initialize']), ('lifecycle', ['nexus', 'install']),
        ('lifecycle', ['nexus', 'start']), ('lifecycle', ['nexus', 'uninstall']),
        ('plan', ['local_plan']), ('setup', ['local'])]
    for mode, selection in choices:
        name = '-'.join([mode, *selection])
        value = {**common.tags(c), 'mode': mode, 'selection': selection}
        put(directory / (name + '.reserved.json'), value)
        put(directory / (name + '.returned.json'), {**value, 'wrapper_exit_confirmed': True,
                                                   'returncode': 3 if name == 'lifecycle-nexus-start' else 0})
    checkpoint = {'format': 11, 'root': str(c.ROOT), 'proposal_sha256': c.args.expected_proposal_sha256,
        'authorization_sha256': c.args.approval_sha256, **c.P['controller_preparation'],
        'owners': {'local': c.P['paths']['server_home']}, 'faults': ['SYNTHETIC_DIFFERENT_FAILURE'],
        'independent_observation': {'worker_in_flight': False}, 'independent_owner_stops': {'local': {}},
        'requests': {'m1v12-local-setup': {'kind': 'setup', 'lane': 'local', 'settled': False,
            'monitor': {'home': c.P['paths']['server_home'], 'high_water': 37}}},
        'collector': collector.checkpoint(collector.initial_state())}
    put(c.ROOT / 'private/controller.json', seal(checkpoint))
    put(c.ROOT / 'public/local-setup-dispatch.json', {'request_id': 'm1v12-local-setup', 'reservation_persisted': True})
    put(c.ROOT / 'public/local-setup-result.json', {'cli_exit': 3, 'started': 10, 'finished': 20,
                                                'reported_state': 'unconfirmed', 'reported_code': 'A_DIFFERENT_FAILURE'})
    return c, directory


def inventory(fixture):
    return common.invocation_inventory(fixture[0], fixture[1])


def check(fixture, **kwargs):
    c, directory = fixture
    def observed(ctx, component):
        return observation.validate_canonical_absence(ctx, component,
            {**absent(ctx, component), 'generation': '', 'running': False, 'ipc_ok': False})
    options = {'task_reader': lambda _: None, 'absence': observed, 'inventory': inventory(fixture)}
    options.update(kwargs)
    return presence.check_component(c, 'connector', **options)


def test_local_failure_proves_unselected_connector_without_erasing_uncertainty(local_only):
    c, _ = local_only
    before = common.sha(c.ROOT / 'private/controller.json')
    result = check(local_only)
    proof = result['unselected_scope_evidence']
    assert proof['basis'] == 'COMPLETED_LOCAL_SETUP_FAILURE_CONNECTOR_NEVER_SELECTED'
    assert result['canonical_absence']['generation'] == ''
    assert result['owner_cleanup_evidence'] == {}
    summary = proof['checkpoint_summary']
    assert summary['cumulative_reserved_admissions'] == 8
    assert summary['cumulative_minimum_observed_tokens'] == 89510
    assert summary['new_observed_tokens'] == 37 and summary['unsettled_requests'] == 1
    assert summary['faults_preserved'] == ['SYNTHETIC_DIFFERENT_FAILURE']
    assert summary['billing_final'] is False and proof['setup_success_inferred'] is False
    assert common.sha(c.ROOT / 'private/controller.json') == before
    assert not (c.ROOT / 'public/final-presence.json').exists()


def test_optional_finished_nexus_stop_has_only_local_effect(local_only):
    c, directory = local_only
    record = {**common.tags(c), 'mode': 'lifecycle', 'selection': ['nexus', 'stop']}
    put(directory / 'lifecycle-nexus-stop.reserved.json', record)
    put(directory / 'lifecycle-nexus-stop.returned.json', {**record, 'wrapper_exit_confirmed': True, 'returncode': 0})
    assert check(local_only)['absent'] is True


@pytest.mark.parametrize('mode,selection', [('operator_bootstrap', ['once']), ('work', ['local', 'useful']),
    ('work', ['connector', 'continuation']), ('remote_setup', ['transfer']), ('plan', ['remote_plan']),
    ('plan', ['connector_host_draft']), ('lifecycle', ['connector', 'install'])])
def test_additional_effect_route_refused(local_only, mode, selection):
    c, directory = local_only
    name = '-'.join([mode, *selection])
    record = {**common.tags(c), 'mode': mode, 'selection': selection}
    put(directory / (name + '.reserved.json'), record)
    put(directory / (name + '.returned.json'), {**record, 'wrapper_exit_confirmed': True, 'returncode': 0})
    with pytest.raises(common.Refused, match='LOCAL_ONLY_HISTORY_REQUIRED'):
        check(local_only)


def test_missing_wrapper_return_refused(local_only):
    (local_only[1] / 'setup-local.returned.json').unlink()
    with pytest.raises(common.Refused, match='INCOMPLETE_INVOCATION_REQUIRES_RECONCILIATION'):
        check(local_only)


@pytest.mark.parametrize('area,name', [('public', 'remote-host-handoff.json'), ('public', 'operator-login-reserved.json'),
    ('public', 'm1v12-local-work-01-dispatch-selection.json'), ('private', 'response-loss.json'),
    ('connector', 'receipt.json'), ('operator', 'profile.json')])
def test_other_phase_artifact_refused(local_only, area, name):
    put(local_only[0].ROOT / area / name, {})
    with pytest.raises(common.Refused):
        check(local_only)


@pytest.mark.parametrize('change', ['owner', 'lane', 'work_request', 'worker', 'seal', 'collector'])
def test_nonlocal_or_unconfirmed_checkpoint_refused(local_only, change):
    c, _ = local_only
    path = c.ROOT / 'private/controller.json'
    value = common.read_json(path)
    if change == 'owner':
        value['owners']['connector'] = c.P['paths']['connector_state']
    elif change == 'lane':
        value['requests']['m1v12-local-setup']['lane'] = 'connector'
    elif change == 'work_request':
        value['requests']['m1v12-local-work-01'] = {'kind': 'work', 'settled': False}
    elif change == 'worker':
        value['independent_observation']['worker_in_flight'] = True
    elif change == 'collector':
        state = collector.initial_state(); state['current_request'] = 'unexpected'
        value['collector'] = collector.checkpoint(state)
    if change != 'seal':
        value = seal(value)
    else:
        value['state_sha256'] = 'wrong'
    put(path, value)
    with pytest.raises((common.Refused, collector.Invalid)):
        check(local_only)


@pytest.mark.parametrize('change', ['missing_result', 'success', 'unfinished', 'wrong_dispatch', 'unreserved'])
def test_requires_finished_local_failure(local_only, change):
    c, _ = local_only
    path = c.ROOT / 'public/local-setup-result.json'
    if change == 'missing_result':
        path.unlink()
    elif change in ('success', 'unfinished'):
        value = common.read_json(path)
        value['cli_exit' if change == 'success' else 'finished'] = 0
        put(path, value)
    else:
        path = c.ROOT / 'public/local-setup-dispatch.json'
        value = common.read_json(path)
        value['request_id' if change == 'wrong_dispatch' else 'reservation_persisted'] = 'wrong' if change == 'wrong_dispatch' else False
        put(path, value)
    with pytest.raises((common.Refused, FileNotFoundError)):
        check(local_only)


def test_no_fault_name_or_token_count_assumption(local_only):
    c, _ = local_only
    path = c.ROOT / 'private/controller.json'
    value = common.read_json(path)
    value['faults'] = []
    value['requests']['m1v12-local-setup']['settled'] = True
    value['requests']['m1v12-local-setup']['monitor']['high_water'] = 100
    put(path, seal(value))
    proof = check(local_only)['unselected_scope_evidence']
    assert proof['checkpoint_summary']['faults_preserved'] == []
    assert proof['checkpoint_summary']['new_observed_tokens'] == 100
    assert proof['checkpoint_summary']['unsettled_requests'] == 0
    assert proof['setup_success_inferred'] is False


def test_history_changed_during_observation_refused(local_only):
    def changed(ctx, component):
        (local_only[1] / 'setup-local.returned.json').unlink()
        return absent(ctx, component)
    with pytest.raises(common.Refused):
        check(local_only, absence=changed)


def test_present_task_never_hidden_by_local_history(local_only):
    with pytest.raises(common.Refused, match='TEMPORARY_TASK_STILL_PRESENT'):
        check(local_only, task_reader=lambda _: object())


def test_real_installed_dataclass_default_is_accepted(local_only):
    site = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/draft/installation/venv/Lib/site-packages')
    sys.path.insert(0, str(site))
    from okto_nexus_connector.daemon import manager
    assert Path(manager.__file__).resolve() == (site / 'okto_nexus_connector/daemon/manager.py').resolve()
    c = local_only[0]
    raw = manager.DaemonStatus(False, None, '', '', '', '', None, False, state='stopped', reason='NO_SERVICE_OWNER',
                              instance_id=c.C['tasks']['connector']['instance_id']).to_json()
    assert raw['generation'] == ''
    assert observation.validate_canonical_absence(c, 'connector', raw)['generation'] == ''


@pytest.mark.parametrize('field,value', [('generation', None), ('generation', False), ('generation', 0),
    ('generation', 'real-generation'), ('state', 'starting'), ('state', 'unknown'), ('pid', 123),
    ('running', True), ('ipc_ok', True), ('instance_id', 'foreign'), ('reason', 'INSTANCE_OWNERSHIP_UNCONFIRMED')])
def test_connector_absence_representation_is_strict(local_only, field, value):
    c = local_only[0]
    raw = {**absent(c, 'connector'), 'generation': '', 'running': False, 'ipc_ok': False}
    raw[field] = value
    with pytest.raises(common.Refused, match='CANONICAL_OWNER_ABSENCE_UNCONFIRMED'):
        observation.validate_canonical_absence(c, 'connector', raw)


def test_nexus_absence_keeps_original_none_contract(local_only):
    c = local_only[0]
    assert observation.validate_canonical_absence(c, 'nexus', absent(c, 'nexus'))['generation'] is None
    with pytest.raises(common.Refused):
        observation.validate_canonical_absence(c, 'nexus', {**absent(c, 'nexus'), 'generation': ''})
