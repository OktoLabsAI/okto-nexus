"""Pure fixtures only: no real authorization, campaign, controller or OS service."""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import hashlib
import json
import socket
import subprocess
import sys

import pytest

import driver_common as common
import invoke
import m1_v12_observation as observation
import m1_v12_confirm_cleanup as cleanup
import confirm_final_presence as presence
import close_campaign as closure

H = 'a' * 64
A = 'b' * 64


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def refused(*_args, **_kwargs):
        raise AssertionError('External effect forbidden in driver qualification')
    monkeypatch.setattr(subprocess, 'Popen', refused)
    monkeypatch.setattr(socket, 'socket', refused)
    monkeypatch.setattr(observation, 'PhysicalProcess', refused)


@pytest.fixture
def context(tmp_path):
    root = tmp_path / 'synthetic-campaign'
    root.mkdir()
    for name in ('public', 'private', 'server', 'connector'):
        (root / name).mkdir()
    policy = {'revision': 12, 'carry_in_admissions': 7, 'carry_in_tokens': 89473,
        'max_new_admissions': 5, 'max_cumulative_admissions': 12}
    value = SimpleNamespace(ROOT=root, args=SimpleNamespace(expected_proposal_sha256=H, approval_sha256=A))
    value.P = {'revision': 12, 'paths': {'campaign_root': str(root)},
        'controller_preparation': {'policy': policy, 'ancestry': {'closed': 'prior-test-only'}},
        'execution_bundle': {'status': 'FROZEN_QUALIFIED', 'files': {}},
        'package_pins': {'python': 'synthetic-python-never-executed'}}
    value.C = {'tasks': {c: {'name': 'synthetic-' + c, 'instance_id': 'instance-' + c}
        for c in ('nexus', 'connector')}}
    value.common_args = lambda: ['--test-only']
    value.env = lambda: {'TEST_ONLY': 'true'}
    return value


def receipt(context):
    # Memory-only synthetic document: never written as an authorization file.
    return {'status': 'USER_APPROVED', 'proposal_revision': 12, 'proposal_sha256': H,
        'campaign_root': str(context.ROOT), **context.P['controller_preparation'],
        'user_quote': 'SYNTHETIC UNIT TEST ONLY - NO EXECUTION AUTHORITY'}


@pytest.mark.parametrize('field,value', [('proposal_revision', 10), ('proposal_sha256', 'c' * 64),
    ('campaign_root', 'prior-campaign'), ('policy', {}), ('ancestry', {}), ('user_quote', ''), ('status', 'PREPARED')])
def test_predecessor_or_incomplete_approval_refused(context, field, value):
    document = receipt(context)
    document[field] = value
    with pytest.raises(common.Refused, match='FRESH_APPROVAL_SCOPE_REQUIRED'):
        common.validate_documents(context.P, document, H, A)


def test_only_frozen_revision_twelve_qualifies_memory_scope(context):
    common.validate_documents(context.P, receipt(context), H, A)
    context.P['execution_bundle']['status'] = 'PENDING'
    with pytest.raises(common.Refused, match='FINAL_FROZEN_BUNDLE_REQUIRED'):
        common.validate_documents(context.P, receipt(context), H, A)


def test_missing_actual_receipt_refuses_before_runtime_import(context, monkeypatch):
    args = SimpleNamespace(proposal='test-only-proposal', expected_proposal_sha256=H,
        approval_path='missing-test-only-receipt', approval_sha256=A)
    def digest(path):
        if path == args.proposal:
            return H
        raise FileNotFoundError(path)
    monkeypatch.setattr(common, 'sha', digest)
    monkeypatch.setattr(common.importlib.util, 'spec_from_file_location',
        lambda *_a: pytest.fail('receipt refusal must precede code loading'))
    with pytest.raises(FileNotFoundError):
        common.gate(args)


def test_owned_path_rejects_other_root_before_any_mutation(context):
    with pytest.raises(common.Refused, match='PATH_OUTSIDE_OWN_ROOT'):
        common.secure_directory(context.ROOT.parent / 'foreign', context.ROOT)
    assert not (context.ROOT.parent / 'foreign').exists()


def test_driver_self_pin_changed_refuses_before_runtime_import(context, monkeypatch):
    args = SimpleNamespace(proposal='test-only-proposal', expected_proposal_sha256=H,
        approval_path='test-only-receipt-in-memory', approval_sha256=A)
    for key, name in common.DRIVERS.items():
        context.P['execution_bundle']['files'][key] = {'path': str(common.HERE / name), 'sha256': common.sha(common.HERE / name)}
    context.P['execution_bundle']['files']['root_driver_invoke']['sha256'] = '0' * 64
    real_sha = common.sha
    monkeypatch.setattr(common, 'sha', lambda p: H if p == args.proposal else A if p == args.approval_path else real_sha(p))
    monkeypatch.setattr(common, 'read_json', lambda p: context.P if p == args.proposal else receipt(context))
    monkeypatch.setattr(common.importlib.util, 'spec_from_file_location',
        lambda *_a: pytest.fail('changed driver must not load runtime code'))
    with pytest.raises(common.Refused, match='ROOT_DRIVER_PIN_CHANGED'):
        common.gate(args)


@pytest.mark.parametrize('foreign,protected', [(False, True), (True, True), (False, False)])
def test_acl_is_scoped_verified_and_refuses_foreign_access(context, monkeypatch, foreign, protected):
    calls, entries = [], []
    class ACL:
        def AddAccessAllowedAceEx(self, _revision, flags, mask, sid):
            entries.append(((0, flags), mask, sid))

        def GetAceCount(self):
            return len(entries)

        def GetAce(self, index):
            item = entries[index]
            return (*item[:2], 'FOREIGN') if foreign and index == 0 else item
    acl = ACL()
    token = SimpleNamespace(Close=lambda: calls.append('token-closed'))
    api = SimpleNamespace(OpenProcessToken=lambda *_a: token, GetTokenInformation=lambda *_a: ('USER',),
        CreateWellKnownSid=lambda *_a: 'SYSTEM', ACL=lambda: acl,
        ACL_REVISION=2, TokenUser=1, WinLocalSystemSid=22, SE_FILE_OBJECT=1,
        DACL_SECURITY_INFORMATION=4, PROTECTED_DACL_SECURITY_INFORMATION=0x80000000,
        ACCESS_ALLOWED_ACE_TYPE=0, ConvertSidToStringSid=lambda v: v,
        SetNamedSecurityInfo=lambda *a: calls.append(a),
        GetNamedSecurityInfo=lambda *_a: SimpleNamespace(GetSecurityDescriptorDacl=lambda: acl,
            GetSecurityDescriptorControl=lambda: (0x1000 if protected else 0, 1)))
    monkeypatch.setitem(sys.modules, 'win32security', api)
    monkeypatch.setitem(sys.modules, 'win32api', SimpleNamespace(GetCurrentProcess=lambda: 'FAKE_PROCESS'))
    monkeypatch.setitem(sys.modules, 'win32con', SimpleNamespace(TOKEN_QUERY=8, OBJECT_INHERIT_ACE=1, CONTAINER_INHERIT_ACE=2))
    monkeypatch.setitem(sys.modules, 'ntsecuritycon', SimpleNamespace(FILE_ALL_ACCESS=2032127))
    target = context.ROOT / 'synthetic-protected-output'
    if foreign or not protected:
        with pytest.raises(common.Refused, match='PRIVATE_ACL_UNCONFIRMED'):
            common.secure_directory(target, context.ROOT)
    else:
        assert common.secure_directory(target, context.ROOT) == target
    writes = [v for v in calls if isinstance(v, tuple)]
    assert len(writes) == 1 and writes[0][0] == str(target)
    assert calls[0] == 'token-closed'


def stub_entry(context, tmp_path, mode='setup'):
    entry = tmp_path / 'synthetic-source.py'
    entry.write_text('# never executed\n')
    context.P['execution_bundle']['files'][mode] = {'path': str(entry), 'sha256': common.sha(entry)}


class Child:
    pid = 1234

    def wait(self):
        return 0

    def communicate(self, _data):
        raise AssertionError('This fixture has no stdin')


def test_dispatch_reserved_before_popen_and_cannot_replay(context, tmp_path):
    stub_entry(context, tmp_path)
    calls = []
    def spawn(argv, **kwargs):
        assert (tmp_path / 'setup-local.reserved.json').exists()
        assert kwargs['env'] == {'TEST_ONLY': 'true'}
        calls.append(argv)
        return Child()
    result = invoke.dispatch(context, 'setup', ['local'], tmp_path, popen=spawn)
    assert result['wrapper_exit_confirmed'] and result['returncode'] == 0
    with pytest.raises(FileExistsError):
        invoke.dispatch(context, 'setup', ['local'], tmp_path, popen=spawn)
    assert len(calls) == 1


def test_spawn_failure_retains_reserved_unknown_effect(context, tmp_path):
    stub_entry(context, tmp_path)
    def refused(*_a, **_k):
        raise OSError('synthetic spawn failure')
    with pytest.raises(OSError):
        invoke.dispatch(context, 'setup', ['local'], tmp_path, popen=refused)
    assert (tmp_path / 'setup-local.reserved.json').exists()
    assert not (tmp_path / 'setup-local.returned.json').exists()
    with pytest.raises(FileExistsError):
        invoke.dispatch(context, 'setup', ['local'], tmp_path, popen=lambda *_a, **_k: pytest.fail('replay'))


def test_unknown_or_force_selection_has_no_reservation(context, tmp_path):
    with pytest.raises(common.Refused, match='FINITE_SELECTION_INVALID'):
        invoke.dispatch(context, 'lifecycle', ['nexus', '--force'], tmp_path)
    assert not list(tmp_path.glob('*.reserved.json'))


def owner(context):
    return {'pid': 321, 'generation': 'g1', 'instance_id': 'instance-nexus', 'component': 'nexus',
        'task': {'name': 'synthetic-nexus', 'digest': H, 'state': 4}, 'birth_filetime': 123456,
        **common.tags(context)}


class Handle:
    def __init__(self, birth=123456, waits=None):
        self.birth_value = birth
        self.waits = iter(waits or [True])
        self.closed = False

    def birth(self):
        return self.birth_value

    def wait(self, _ms):
        return next(self.waits)

    def close(self):
        self.closed = True


def select_fixture(context):
    value = owner(context)
    common.public_save(context, 'nexus-owner-selection.json', value)
    return value


def test_pid_reuse_never_proves_exit(context):
    selected = select_fixture(context)
    handle = Handle(birth=selected['birth_filetime'] + 1)
    with pytest.raises(common.Refused, match='PROCESS_BIRTH_CHANGED'):
        observation.watch(context, 'nexus', 10, observe=lambda *_a: selected, process=lambda _pid: handle)
    assert handle.closed
    assert not (context.ROOT / 'public/nexus-exit-proof.json').exists()


@pytest.mark.parametrize('field', ['generation', 'instance_id', 'pid'])
def test_changed_owner_refuses_retained_handle_watch(context, field):
    selected = select_fixture(context)
    current = {**selected, field: 'changed'}
    handle = Handle()
    with pytest.raises(common.Refused, match='OWNER_CHANGED'):
        observation.watch(context, 'nexus', 10, observe=lambda *_a: current, process=lambda _pid: handle)
    assert handle.closed
    assert not (context.ROOT / 'public/nexus-exit-proof.json').exists()


def test_physical_exit_proof_retains_exact_identity(context):
    selected = select_fixture(context)
    handle = Handle(waits=[False, True])
    result = observation.watch(context, 'nexus', 10, observe=lambda *_a: selected,
        process=lambda _pid: handle, clock=lambda: 0)
    assert handle.closed and result['retained_handle'] and result['wait_result'] == 0
    assert all(result[k] == selected[k] for k in (*observation.IDENTITY, 'birth_filetime'))
    assert result['force_used'] is False


def test_watch_timeout_never_fabricates_exit(context):
    selected = select_fixture(context)
    handle = Handle(waits=[False])
    ticks = iter([0, 0, 11])
    with pytest.raises(TimeoutError):
        observation.watch(context, 'nexus', 10, observe=lambda *_a: selected,
            process=lambda _pid: handle, clock=lambda: next(ticks))
    assert handle.closed
    assert not (context.ROOT / 'public/nexus-exit-proof.json').exists()
    assert common.read_json(context.ROOT / 'public/nexus-exit-watch-timeout.json')['exit_confirmed'] is False


@pytest.mark.parametrize('field,value', [('generation', 'other'), ('birth_filetime', 999),
    ('instance_id', 'other'), ('retained_handle', False), ('force_used', True), ('wait_result', 258)])
def test_cleanup_refuses_changed_identity_or_unconfirmed_exit(context, field, value):
    selected = owner(context)
    proof = {**selected, 'retained_handle': True, 'exit_confirmed': True, 'wait_result': 0, 'force_used': False}
    proof[field] = value
    with pytest.raises(common.Refused):
        cleanup.validate_exit(selected, proof, {'state': 'DRAINED', 'generation': 'g1'},
            SimpleNamespace(state=3, digest=H), context.C['tasks']['nexus'])


def test_selected_owner_removal_needs_physical_cleanup(context):
    common.reserve(context.ROOT / 'public/lifecycle-nexus-install.json', {'test_only': True})
    with pytest.raises(FileNotFoundError):
        presence.check_component(context, 'nexus', task_reader=lambda _name: None, inventory={})


def install_only(context, tmp_path, monkeypatch):
    directory = tmp_path / 'driver-root/runtime-private'
    directory.mkdir(parents=True)
    monkeypatch.setattr(common, 'HERE', directory.parent)
    for selection in (['initialize'], ['nexus', 'install']):
        value = {**common.tags(context), 'mode': 'lifecycle', 'selection': selection}
        name = '-'.join(['lifecycle', *selection])
        common.reserve(directory / (name + '.reserved.json'), value)
        common.reserve(directory / (name + '.returned.json'), {**value, 'returncode': 0, 'wrapper_exit_confirmed': True})
    public = context.ROOT / 'public'
    value = {'component': 'nexus', 'action': 'install', 'task_name': context.C['tasks']['nexus']['name'], 'proposal_sha256': H}
    common.reserve(public / 'lifecycle-nexus-install.json', value)
    common.reserve(public / 'lifecycle-nexus-install-result.json', {**value, 'returncode': 0})
    return directory


def absent(context, component):
    return {'state': 'stopped', 'reason': 'NO_SERVICE_OWNER', 'instance_id': context.C['tasks'][component]['instance_id'],
        'pid': None, 'generation': None}


def test_install_only_proof_is_independently_rechecked_not_boolean(context, tmp_path, monkeypatch):
    directory = install_only(context, tmp_path, monkeypatch)
    live = {'canonical_absence': absent(context, 'nexus'), 'task_state': 3, 'scheduler_last_result': 0x41303,
        'control_sha256': H, 'installation_receipt_sha256': A}
    monkeypatch.setattr(cleanup, 'live_never_started', lambda *_a: dict(live))
    proof = {**common.tags(context), 'kind': 'NEVER_STARTED_OWNER_ABSENT', 'component': 'nexus',
        'owned_pid_birth_exit_confirmed': False, 'base_evidence': cleanup.never_started_inputs(context, 'nexus'),
        'live_evidence': live}
    assert cleanup.validate_never_started(context, proof)
    current_uninstall = {**common.tags(context), 'mode': 'lifecycle', 'selection': ['nexus', 'uninstall']}
    common.reserve(directory / 'lifecycle-nexus-uninstall.reserved.json', current_uninstall)
    assert cleanup.validate_never_started(context, proof, allow_current_uninstall=True)
    monkeypatch.setattr(cleanup, 'live_never_started', lambda *_a: {**live, 'control_sha256': 'changed'})
    with pytest.raises(common.Refused, match='LIVE_ABSENCE_PROOF_CHANGED'):
        cleanup.validate_never_started(context, proof, allow_current_uninstall=True)


@pytest.mark.parametrize('change', [None, 'task_running', 'task_result_zero', 'launch_requested', 'generation', 'definition_change'])
def test_live_install_only_requires_canonical_absence_and_pristine_scheduler_control(context, monkeypatch, change):
    context.P['paths']['server_home'] = str(context.ROOT / 'server')
    home = Path(context.P['paths']['server_home'])
    for name in ('synthetic-installation.json', 'synthetic-control.json'):
        (home / name).write_text('{}')
    expected = context.C['tasks']['nexus']
    task = SimpleNamespace(state=4 if change == 'task_running' else 3,
        last_result=0 if change == 'task_result_zero' else 0x41303, digest=H)
    control = {'desired': 'running'}
    if change == 'launch_requested':
        control['launch_requested'] = True
    if change == 'generation':
        control['generation'] = 'ambiguous-owner'
    class Service:
        def __init__(self, selected_home, _database):
            assert selected_home == home
            self.path = home / 'synthetic-installation.json'

        def observe(self):
            if change == 'definition_change':
                raise ValueError('synthetic changed native definition')
            return {'name': expected['name'], 'instance_id': expected['instance_id']}, task

        def control(self, _receipt):
            return control
    monkeypatch.setitem(sys.modules, 'okto_nexus.adapters.outbound.service_manager.installation',
        SimpleNamespace(ServerInstallation=Service, CONTROL_NAME='synthetic-control.json'))
    monkeypatch.setattr(cleanup, 'canonical_absence', absent)
    if change is None:
        result = cleanup.live_never_started(context, 'nexus')
        assert result['scheduler_last_result'] == 0x41303 and result['canonical_absence']['pid'] is None
        assert result['control_sha256'] == common.sha(home / 'synthetic-control.json')
    else:
        with pytest.raises((common.Refused, ValueError)):
            cleanup.live_never_started(context, 'nexus')


@pytest.mark.parametrize('mode,selection', [('lifecycle', ['nexus', 'start']), ('plan', ['local_plan']),
    ('setup', ['local']), ('work', ['connector', 'useful']), ('remote_setup', ['transfer'])])
def test_install_only_rejects_every_possible_explicit_or_implicit_start(context, tmp_path, monkeypatch, mode, selection):
    directory = install_only(context, tmp_path, monkeypatch)
    value = {**common.tags(context), 'mode': mode, 'selection': selection}
    name = '-'.join([mode, *selection])
    common.reserve(directory / (name + '.reserved.json'), value)
    common.reserve(directory / (name + '.returned.json'), {**value, 'returncode': 0, 'wrapper_exit_confirmed': True})
    with pytest.raises(common.Refused, match='START_OR_IMPLICIT_START_SELECTED'):
        cleanup.never_started_inputs(context, 'nexus')


def test_install_only_refuses_unknown_outer_dispatch_without_success_marker(context, tmp_path, monkeypatch):
    directory = install_only(context, tmp_path, monkeypatch)
    common.reserve(directory / 'remote_setup-transfer.reserved.json',
        {**common.tags(context), 'mode': 'remote_setup', 'selection': ['transfer']})
    with pytest.raises(common.Refused, match='INCOMPLETE_INVOCATION_REQUIRES_RECONCILIATION'):
        cleanup.never_started_inputs(context, 'nexus')


def test_missing_task_does_not_hide_remote_effect_without_postcheck(context):
    inventory = {'remote': {'mode': 'remote_setup', 'selection': ['transfer'], 'returncode': 2}}
    with pytest.raises(common.Refused, match='POSSIBLE_UNSELECTED_START'):
        presence.check_component(context, 'connector', task_reader=lambda _n: None,
            inventory=inventory, absence=absent)
    with pytest.raises(FileNotFoundError):
        presence.remote_helpers(context, inventory)


def test_never_installed_requires_positive_canonical_absence(context):
    inventory = {'initialize': {'mode': 'lifecycle', 'selection': ['initialize'], 'returncode': 0}}
    def unconfirmed(*_a):
        raise common.Refused('CANONICAL_OWNER_ABSENCE_UNCONFIRMED')
    with pytest.raises(common.Refused, match='CANONICAL_OWNER_ABSENCE_UNCONFIRMED'):
        presence.check_component(context, 'connector', task_reader=lambda _n: None,
            inventory=inventory, absence=unconfirmed)
    result = presence.check_component(context, 'connector', task_reader=lambda _n: None,
        inventory=inventory, absence=absent)
    assert result['canonical_absence']['pid'] is None and result['owner_cleanup_evidence'] == {}


def test_no_controller_closure_requires_no_model_capable_selection(context):
    final = {'tasks': {c: {'canonical_absence': absent(context, c)} for c in ('nexus', 'connector')}}
    inventory = {'init': {'mode': 'lifecycle', 'selection': ['initialize'], 'returncode': 0}}
    result = closure.before_controller_summary(context, inventory, final)
    assert result['new_reserved_admissions'] == 0 and result['cumulative_minimum_observed_tokens'] == 89473
    inventory['possible'] = {'mode': 'setup', 'selection': ['local'], 'returncode': 2}
    with pytest.raises(common.Refused, match='NO_CONTROLLER_EFFECT_SCOPE_UNCONFIRMED'):
        closure.before_controller_summary(context, inventory, final)


def seal(value):
    unsealed = {k: v for k, v in value.items() if k != 'state_sha256'}
    value['state_sha256'] = hashlib.sha256(json.dumps(unsealed, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value


def checkpoint(context):
    return seal({'format': 11, 'root': str(context.ROOT), 'policy': context.P['controller_preparation']['policy'],
        'ancestry': context.P['controller_preparation']['ancestry'], 'proposal_sha256': H, 'authorization_sha256': A,
        'requests': {'synthetic-setup': {'kind': 'setup', 'monitor': {'high_water': 17}, 'settled': True},
            'synthetic-work': {'kind': 'work', 'settled': False}}, 'faults': ['SYNTHETIC_OBSERVATION_UNKNOWN']})


def test_closure_derives_counts_and_preserves_uncertainty(context):
    value = checkpoint(context)
    before = deepcopy(value)
    result = closure.checkpoint_summary(context, value, {'known_observed_tokens': 23})
    assert result['cumulative_reserved_admissions'] == 9
    assert result['new_reserved_admissions'] == 2
    assert result['cumulative_minimum_observed_tokens'] == 89513
    assert result['new_observed_tokens'] == 40 and result['billing_final'] is False
    assert result['unsettled_requests'] == 1 and result['faults_preserved'] == value['faults']
    assert before == value


def test_checkpoint_mutation_refused(context):
    value = checkpoint(context)
    value['faults'] = []
    with pytest.raises(common.Refused, match='CHECKPOINT_SCOPE_OR_SEAL_INVALID'):
        closure.checkpoint_summary(context, value, {'known_observed_tokens': 0})


def test_incomplete_wrapper_refuses_closure(context, tmp_path):
    common.reserve(tmp_path / 'setup-local.reserved.json', {**common.tags(context), 'mode': 'setup', 'selection': ['local']})
    with pytest.raises(FileNotFoundError):
        closure.verify_wrappers(context, tmp_path)


def test_completed_wrapper_is_only_exit_evidence(context, tmp_path):
    value = {**common.tags(context), 'mode': 'setup', 'selection': ['local']}
    common.reserve(tmp_path / 'setup-local.reserved.json', value)
    common.reserve(tmp_path / 'setup-local.returned.json', {**value, 'wrapper_exit_confirmed': True, 'returncode': 2})
    result = closure.verify_wrappers(context, tmp_path)
    assert result['setup-local.reserved.json']['returncode'] == 2


def test_all_runtime_sources_compile_without_execution():
    for filename in common.DRIVERS.values():
        path = Path(__file__).parent / filename
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
