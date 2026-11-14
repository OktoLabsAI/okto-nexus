"""Revision16 local14/15 executable; remote16/17 held behind separate qualification."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import argparse
import hashlib
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
CONTROL, ROOT = HERE.parent, HERE.parent.parent
_context = None

def require(value, code):
    if not value: raise RuntimeError(code)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pinned(pin):
    require(sha(pin['path']) == pin['sha256'], 'AMENDMENT_PIN_CHANGED')
    return Path(pin['path'])

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value

def python_utf8(argv, interpreter):
    require(isinstance(argv, list) and argv and argv[0] == interpreter
        and all(isinstance(arg, str) for arg in argv), 'PYTHON_INTERPRETER_CHANGED')
    return [argv[0], '-X', 'utf8', *argv[1:]]

def parser():
    p = argparse.ArgumentParser()
    p.add_argument('--amendment', required=True)
    p.add_argument('--expected-amendment-sha256', required=True)
    return p

def current_commands(original, interpreter):
    value={key:deepcopy(original[key]) for key in ('tasks','service_selection_args','required_parent_path','origin')}
    value['steps']=[deepcopy(step) for step in original['steps'] if step.get('component')=='nexus']
    for step in value['steps']:step['argv']=python_utf8([interpreter,*step['argv'][1:]],interpreter)
    value['scope']='Revision16 local14/15 only; remote16/17 selectors held, allocation retained.'
    value['counts']={'explicit_lifecycle_commands':4,'canonical_environment_upgrade_commands':2,
        'task_installations':1,'explicit_scheduler_starts':1,'implicit_starts':0,
        'new_model_admissions_max':4,'cumulative_model_admissions_max':17,'executable_local_admissions_max':2,'remote_selectors_enabled':False}
    return value

def verify_package(amendment, *, prefix=None):
    installed = json.loads(pinned(amendment['installation']).read_bytes())
    require(installed['status'] == 'INSTALLED_VERIFIED' and installed['pip_check']['returncode'] == 0, 'NEW_INSTALLATION_REQUIRED')
    require(Path(installed['python_prefix']).resolve() == (HERE / 'package/venv').resolve()
        and Path(prefix or sys.prefix).resolve() == Path(installed['python_prefix']).resolve(), 'INSTALLED_PREFIX_MISMATCH')
    require(installed['wheels'] == amendment['wheels'], 'WHEELS_CHANGED')
    for pin in [*installed['wheels'].values(), *installed['files']]: pinned(pin)
    for path, digest in installed['python_images'].items(): require(sha(path) == digest, 'PYTHON_IMAGE_CHANGED')
    return installed


def verify_technical_predecessor(pin):
    proof=json.loads(pinned(pin).read_bytes())
    require(proof['status']=='CLOSED_REVISION15_WITH_CONTROL_RECEIPT_UNCONFIRMED'
        and Path(proof['root']).resolve()==CONTROL/'work-revision15','PREDECESSOR_SCOPE_CHANGED')
    for item in proof['files'].values():pinned(item)
    checkpoint=json.loads(pinned(proof['files']['checkpoint']).read_bytes())
    require(set(checkpoint['requests'])=={'m1v15-local-useful-13'}
        and checkpoint['requests']['m1v15-local-useful-13']['settled'] is True
        and checkpoint['requests']['m1v15-local-useful-13']['canonical_stage']=='CANCELLED'
        and checkpoint['faults']==['WORK_TERMINAL_FAILED'],'PREDECESSOR_CHECKPOINT_CHANGED')
    companion=json.loads(pinned(proof['files']['companion']).read_bytes())
    require(companion['cumulative_observed_tokens']==341276 and companion['charged_reservations']==13
        and companion['original_checkpoint_and_closure_untouched'] is True
        and companion['interrupt']['receipt_stage']=='SUBMITTED'
        and companion['interrupt']['completion_receipt_confirmed'] is False
        and companion['request14_selected'] is False,'PREDECESSOR_UNCERTAINTY_CHANGED')
    closure=json.loads(pinned(proof['files']['closure']).read_bytes())
    require(closure['status']=='CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED'
        and closure['closed_without_force'] is True and closure['unsettled_requests']==0,
        'CLOSED_PREDECESSOR_REQUIRED')
    return True


def gate(args):
    global _context
    require(sha(args.amendment) == args.expected_amendment_sha256, 'AMENDMENT_CHANGED')
    if _context is not None:
        require(not (_context.PUBLIC / 'closure.json').exists(), 'ALREADY_CLOSED')
        return _context
    amendment = json.loads(Path(args.amendment).read_bytes())
    require(amendment['format'] == 'okto.m1.v16.work-revision16'
        and Path(amendment['work_root']).resolve() == HERE
        and Path(amendment['campaign_root']).resolve() == ROOT
        and Path(amendment['control_root']).resolve() == CONTROL
        and CONTROL.name == 'successor14' and HERE.name == 'work-revision16', 'AMENDMENT_SCOPE_CHANGED')
    require(amendment['request_ids'] == {'useful':'m1v16-local-useful-14','continuation':'m1v16-local-continuation-15',
        'remote_useful':'m1v16-remote-useful-16','remote_continuation':'m1v16-remote-continuation-17'}
        and amendment['future_force_authorized'] is False, 'FINITE_REQUEST_SCOPE_CHANGED')
    for pin in [*amendment['sources'].values(), *amendment['basis'].values()]: pinned(pin)
    for key, name in {'context':'request_context.py','entry':'request_entry.py','invoke':'invoke_request.py',
        'common':'driver_common.py','work':'local_work.py','cohort':'cohort.py','lifecycle':'lifecycle.py',
        'authorize':'authorize_local.py','close':'close_campaign.py','final_presence':'confirm_final_presence.py'}.items():
        require(Path(amendment['sources'][key]['path']).resolve() == HERE / name, 'ENTRY_SOURCE_PATH_CHANGED')
    require({Path(p['path']).resolve() for p in amendment['sources'].values()} >=
        {p.resolve() for p in (HERE / 'modules').glob('*.py')}, 'UNPINNED_CONTROLLER_SOURCE')
    original = amendment['original']
    require(sha(original['proposal']) == original['proposal_sha256']
        and sha(original['approval']) == original['approval_sha256'], 'ORIGINAL_AUTHORITY_CHANGED')
    proposal = json.loads(Path(original['proposal']).read_bytes())
    receipt = json.loads(Path(original['approval']).read_bytes())
    common = module('driver_common', pinned(amendment['sources']['common']))
    common.validate_documents(proposal, receipt, original['proposal_sha256'], original['approval_sha256'])
    for pin in proposal['execution_bundle']['files'].values(): pinned(pin)
    require(amendment['source_authority'] == {'proposal_sha256': original['proposal_sha256'],
        'approval_sha256': original['approval_sha256']}, 'AUTHORITY_BINDING_CHANGED')
    plan=json.loads(pinned(amendment['execution_plan']).read_bytes())
    require(amendment['policy']==plan['policy'] and amendment['remote_execution_enabled'] is False
        and amendment['policy']['revision']==16 and amendment['policy']['max_cumulative_admissions']==17
        and amendment['policy']['carry_in_tokens']==341276 and amendment['policy']['carry_in_admissions']==13,
        'SELECTED_TECHNICAL_POLICY_CHANGED')
    verify_technical_predecessor(amendment['technical_predecessor'])
    installed = verify_package(amendment)
    probe = json.loads(pinned(amendment['installed_probe']).read_bytes())
    require(probe.get('status') == 'CANONICAL_PROBE60_PASS'
        and probe.get('installation_sha256') == amendment['installation']['sha256']
        and probe.get('candidate', {}).get('executable') == installed['python']
        and probe['candidate'].get('environment_prefix') == installed['python_prefix'], 'NEW_PACKAGE_PROBE_REQUIRED')
    require(sha(proposal['paths']['codex_executable']) == proposal['native_selection']['fingerprint'].split(':', 1)[1], 'NATIVE_PIN_CHANGED')
    companion = json.loads(pinned(amendment['basis']['companion']).read_bytes())
    require(companion['status']=='CANCELLED_WORK_NORMAL_CLOSURE_CONFIRMED_NO_M1_ACCEPTANCE'
        and companion['normal_cleanup']['all_three_retained_handles_exited'] is True
        and companion['normal_cleanup']['tasks_absent'] is True
        and companion['normal_cleanup']['force_used'] is False
        and companion['original_checkpoint_and_closure_untouched'] is True
        and companion['cumulative_observed_tokens']==341276 and companion['charged_reservations']==13,
        'CLOSED_PREDECESSOR_REQUIRED')
    predecessor=json.loads(pinned(amendment['technical_predecessor']).read_bytes())
    for name in ('physical_exit','cleanup_proof','uninstall','final_presence','closure'):
        pinned(predecessor['files'][name])
    original_context = module('campaign_context', pinned(proposal['execution_bundle']['files']['context']))
    commands = json.loads(pinned(amendment['commands']).read_bytes())
    original_commands = json.loads(pinned(proposal['execution_bundle']['commands']).read_bytes())
    expected_commands = current_commands(original_commands,installed['python'])
    require(commands == expected_commands and len(commands['steps']) == 4, 'FINITE_COMMANDS_CHANGED')
    original_args = SimpleNamespace(proposal=original['proposal'], expected_proposal_sha256=original['proposal_sha256'],
        approval_path=original['approval'], approval_sha256=original['approval_sha256'])
    base = original_context.Context(original_args, [], proposal, commands, ROOT, HERE / 'modules')
    context = Context(base, args, amendment, installed)
    require(not (context.PUBLIC / 'closure.json').exists(), 'ALREADY_CLOSED')
    common.HERE, common.gate, common.parser = HERE, gate, parser
    common.owned_path(HERE, CONTROL)
    for path in (context.PUBLIC,context.PRIVATE,HERE/'runtime-private',HERE/'package'):
        common.owned_path(path,HERE)
    context.common = common
    original_context.load = lambda: context
    original_context.reserve_json = common.reserve
    _context = context
    return context

class Context:
    def __init__(self, base, args, amendment, installed):
        self.base, self.args, self.amendment_args = base, base.args, args
        self.amendment, self.installed = amendment, installed
        self.P, self.C = deepcopy(base.P), deepcopy(base.C)
        self.ROOT, self.CONTROL = ROOT, CONTROL
        self.PUBLIC, self.PRIVATE, self.modules = HERE / 'public', HERE / 'private', HERE / 'modules'
        self.remaining = []
        self.P['package_pins'] = {**installed, 'status': 'QUALIFIED_NEW_INSTALLATION'}
        self.P['request_ids']['work'] = list(amendment['request_ids'].values())
        self.P['finite_work']['maximum_productive_admissions'] = 4
        self.P['finite_work']['maximum_cumulative_admissions'] = 17
        self.P['finite_work'].pop('maximum_confirmed_productive_including_history', None)
        self.P['finite_work']['historical_charged_reservations'] = 13
        self.P['finite_work']['counter_semantics'] = 'Thirteen historical reservations and341276 observed tokens retained; four new finite IDs, maximum17 cumulative. Remote selectors remain closed. No refund or historical replay.'
        self.P['controller_preparation']['policy'] = deepcopy(amendment['policy'])
        self.P['controller_preparation']['ancestry'] = deepcopy(amendment['controller_ancestry'])
        self.P['adoption']['predecessor_work_checkpoint_pin'] = deepcopy(amendment['initial_work_checkpoint'])
        self.P['adoption']['expected_historical_grants'] = deepcopy(amendment['expected_historical_grants'])
        self.P['adoption']['predecessor_closure_pin'] = deepcopy(amendment['basis']['companion'])
        self.P['adoption']['predecessor_session_id'] = amendment['predecessor_session_id']
        for key, pin in amendment['bundle_overrides'].items(): self.P['execution_bundle']['files'][key] = deepcopy(pin)

    def env(self): return self.base.env()

    def require_ready(self):
        from cohort import recovery_ready
        return recovery_ready(self)

    def common_args(self):
        return ['--amendment', self.amendment_args.amendment,
            '--expected-amendment-sha256', self.amendment_args.expected_amendment_sha256]

    def controller(self, *, create=False):
        require(not create, 'DERIVED_CONTROLLER_MUST_BE_PREPARED')
        sys.path.insert(0, str(self.modules))
        from fresh_work_controller import FreshWorkController
        return FreshWorkController(self.PRIVATE / 'controller.json', self.ROOT, original_control_root=self.CONTROL,
            amendment_path=self.amendment_args.amendment, amendment_sha256=self.amendment_args.expected_amendment_sha256,
            approval_path=self.args.approval_path, approval_sha256=self.args.approval_sha256,
            expected_proposal_sha256=self.args.expected_proposal_sha256)

    def stop_argv(self, component):
        require(component == 'nexus', 'LOCAL_ONLY')
        return python_utf8([self.P['package_pins']['python'], '-I', '-B', str(HERE / 'request_entry.py'),
            *self.common_args(), 'lifecycle', 'nexus', 'stop'], self.P['package_pins']['python'])

    def validate_fresh_work(self, document, authorization_basis):
        pin = self.amendment['initial_work_checkpoint']
        require(sha(self.PRIVATE / 'predecessor-work-checkpoint.json') == pin['sha256'], 'HISTORY_SNAPSHOT_CHANGED')
        require(sha(pin['path']) == authorization_basis['work_checkpoint_sha256'], 'AUTHORIZED_CHECKPOINT_CHANGED')
        require(document.get('session_id') == self.amendment['predecessor_session_id']
            and document.get('work', {}).get('client_intent_id') == 'm1v15-local-useful-13', 'FAILED_PREDECESSOR_CHANGED')
        return True

def prepare(context):
    require(not context.PUBLIC.exists() and not context.PRIVATE.exists(), 'PREPARATION_ALREADY_SELECTED')
    basis = context.amendment['basis']
    initial = pinned(context.amendment['initial_work_checkpoint'])
    sys.path.insert(0, str(context.modules))
    from fresh_work_controller import prepare_derived
    values = [json.loads(pinned(basis[key]).read_bytes()) for key in ('checkpoint', 'companion', 'accounting')]
    derived = prepare_derived(*values, source_pins=basis)
    context.PUBLIC.mkdir()
    context.common.secure_directory(context.PRIVATE, HERE)
    context.common.private_outputs()
    adopted = json.loads(pinned(basis['adoption']).read_bytes())
    context.common.public_save(context, 'adopt-local-result.json', {**adopted,
        'carried_from': basis['adoption'], 'fresh_adoption_claimed': False})
    (context.PRIVATE / 'predecessor-work-checkpoint.json').write_bytes(initial.read_bytes())
    context.common.reserve(context.PRIVATE / 'controller.json', derived)
    context.common.public_save(context, 'root-driver-preparation.json', {'status': 'FRESH_LOCAL_CONTEXT_PREPARED',
        'controller_sha256': sha(context.PRIVATE / 'controller.json'), 'carried_adoption_proof': True,
        'fresh_adoption_claimed': False, 'new_model_reservations': 0, 'provider_accessed': False,
        'service_action': False, 'initial_cumulative_tokens': 341276, 'initial_cumulative_reservations': 13})
    return 0
