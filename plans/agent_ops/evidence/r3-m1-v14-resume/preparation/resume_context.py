"""Exact v14 amendment adapter; original campaign and installation remain pinned."""
from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
CONTROL = HERE.parent
ROOT = CONTROL.parent
_context = None


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def python_utf8(argv, interpreter):
    require(isinstance(argv, list) and argv and argv[0] == interpreter, 'PYTHON_INTERPRETER_CHANGED')
    require(all(isinstance(arg, str) for arg in argv), 'PYTHON_ARGV_INVALID')
    return [argv[0], '-X', 'utf8', *argv[1:]]


def pinned(pin):
    require(sha(pin['path']) == pin['sha256'], 'AMENDMENT_PIN_CHANGED')
    return Path(pin['path'])


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def parser():
    p = argparse.ArgumentParser()
    p.add_argument('--amendment', required=True)
    p.add_argument('--expected-amendment-sha256', required=True)
    return p


def gate(args):
    global _context
    if _context is not None:
        require(not (_context.PUBLIC / 'closure.json').exists(), 'RESUME_ALREADY_CLOSED')
        return _context
    require(sha(args.amendment) == args.expected_amendment_sha256, 'AMENDMENT_CHANGED')
    amendment = json.loads(Path(args.amendment).read_bytes())
    require(amendment['format'] == 'okto.m1.v14.resume-request01'
        and Path(amendment['resume_root']).resolve() == HERE
        and Path(amendment['control_root']).resolve() == CONTROL
        and CONTROL.name == 'successor14' and HERE.name == 'resume-request01', 'RESUME_SCOPE_CHANGED')
    for pin in amendment['sources'].values():
        pinned(pin)
    for key, filename in (('context', 'resume_context.py'), ('entry', 'resume_entry.py'),
                          ('invoke', 'invoke_resume.py'), ('work', 'resume_work.py')):
        require(Path(amendment['sources'][key]['path']).resolve() == HERE / filename,
                'RESUME_ENTRY_PATH_CHANGED')
    module_root = Path(amendment['sources']['resumed_controller']['path']).parent
    declared = {Path(pin['path']).resolve() for pin in amendment['sources'].values()}
    require(all(p.resolve() in declared for p in module_root.glob('*.py')), 'UNPINNED_CONTROLLER_SOURCE')
    for pin in amendment['basis'].values():
        pinned(pin)
    original = amendment['original']
    require(sha(original['proposal']) == original['proposal_sha256'], 'ORIGINAL_PROPOSAL_CHANGED')
    proposal = json.loads(Path(original['proposal']).read_bytes())
    original_context = module('campaign_context', pinned(proposal['execution_bundle']['files']['context']))
    previous = sys.argv
    try:
        sys.argv = ['original-v14-gate', '--proposal', original['proposal'],
            '--expected-proposal-sha256', original['proposal_sha256'],
            '--approval-path', original['approval'], '--approval-sha256', original['approval_sha256']]
        base = original_context.load()  # exact original approval, policy, product/native/47 source pins
    finally:
        sys.argv = previous
    require(base.CONTROL == CONTROL and base.ROOT == ROOT, 'ORIGINAL_CONTROL_CHANGED')
    require(amendment['policy'] == base.P['controller_preparation']['policy'], 'POLICY_CHANGED')
    closure = json.loads(pinned(amendment['basis']['closure']).read_bytes())
    require(closure['controller_checkpoint_sha256'] == amendment['basis']['checkpoint']['sha256']
        and closure['closed_without_force'] and closure['all_temporary_tasks_absent']
        and closure['cumulative_reserved_admissions'] == 10
        and closure['cumulative_minimum_observed_tokens'] == 134199, 'CLOSED_V14_REQUIRED')
    context = Context(base, args, amendment)
    require(not (context.PUBLIC / 'closure.json').exists(), 'RESUME_ALREADY_CLOSED')
    common = module('driver_common', pinned(proposal['execution_bundle']['files']['root_driver_common']))
    common.owned_path(HERE, CONTROL)
    common.owned_path(context.PUBLIC, CONTROL)
    common.owned_path(context.PRIVATE, CONTROL)
    common.HERE = HERE
    common.gate = gate
    common.parser = parser
    # All original helpers now see new evidence/invocation paths; control identity
    # and all owned homes/task commands remain original v14.
    original_context.load = lambda: context
    original_context.reserve_json = common.reserve
    context.common = common
    _context = context
    return context


class Context:
    def __init__(self, base, args, amendment):
        self.base = base
        self.args = base.args
        self.amendment_args = args
        self.amendment = amendment
        self.P, self.C, self.ROOT, self.CONTROL = base.P, deepcopy(base.C), base.ROOT, base.CONTROL
        for step in self.C['steps']:
            step['argv'] = python_utf8(step['argv'], self.P['package_pins']['python'])
        self.PUBLIC, self.PRIVATE = HERE / 'public', HERE / 'private'
        self.modules = Path(amendment['sources']['resumed_controller']['path']).parent
        self.remaining = []

    def env(self):
        return self.base.env()

    def common_args(self):
        return ['--amendment', self.amendment_args.amendment,
            '--expected-amendment-sha256', self.amendment_args.expected_amendment_sha256]

    def controller(self, *, create=False):
        require(not create, 'DERIVED_CONTROLLER_MUST_BE_PREPARED')
        sys.path.insert(0, str(self.modules))
        from resumed_controller import ResumedController
        return ResumedController(self.PRIVATE / 'controller.json', self.ROOT,
            original_control_root=self.CONTROL,
            first_dispatch_receipt=self.PRIVATE / 'first-dispatch.json',
            approval_path=self.args.approval_path, approval_sha256=self.args.approval_sha256,
            expected_proposal_sha256=self.args.expected_proposal_sha256)

    def lifecycle_script(self):
        return HERE / 'resume_entry.py'

    def stop_argv(self, component):
        require(component == 'nexus', 'LOCAL_RESUME_ONLY')
        return python_utf8([self.P['package_pins']['python'], '-I', '-B', str(self.lifecycle_script()),
            *self.common_args(), 'lifecycle', component, 'stop'], self.P['package_pins']['python'])

    def validate_resumed_work(self, document, text, revision):
        """Initial resume only; later control gates must not repin mutable work."""
        pin = self.amendment['initial_work_checkpoint']
        pinned(pin)
        require(document == json.loads(Path(pin['path']).read_bytes()), 'WORK_DOCUMENT_CHANGED')
        work = document.get('work', {})
        expected = self.amendment['initial_work_selection']
        require(document.get('session_id') == expected['session_id']
            and all(work.get(k) == expected[k] for k in
                ('client_intent_id', 'request_hash', 'intent', 'state', 'has_text', 'action'))
            and work.get('request_context') == expected['request_context'], 'RESUMED_WORK_SELECTION_CHANGED')
        request = dict(work['request_context'], text=text)
        require(revision(request) == work['request_hash'], 'RESUMED_PROMPT_CHANGED')
        return True


def prepare(context):
    require(not context.PUBLIC.exists() and not context.PRIVATE.exists(), 'PREPARATION_ALREADY_SELECTED')
    common = context.common
    context.PUBLIC.mkdir()
    common.secure_directory(context.PRIVATE, HERE)
    common.private_outputs()
    # Only original public authorization/adoption and the pinned private history
    # snapshot are carried, without asserting a fresh adoption or new grant.
    for label in ('adoption', 'authorization_review', 'authorization_apply'):
        source = pinned(context.amendment['basis'][label])
        (context.PUBLIC / source.name).write_bytes(source.read_bytes())
    source = pinned(context.amendment['basis']['predecessor_work_snapshot'])
    (context.PRIVATE / 'predecessor-work-checkpoint.json').write_bytes(source.read_bytes())
    source = pinned(context.amendment['initial_work_checkpoint'])
    (context.PRIVATE / 'initial-resumed-work-checkpoint.json').write_bytes(source.read_bytes())
    sys.path.insert(0, str(context.modules))
    from resumed_controller import prepare_derived
    basis = context.amendment['basis']
    values = [json.loads(pinned(basis[label]).read_bytes()) for label in
        ('checkpoint', 'work_result', 'closure', 'canonical_absence', 'work_returned')]
    derived = prepare_derived(*values, source_pins=basis)
    common.reserve(context.PRIVATE / 'controller.json', derived)
    common.public_save(context, 'root-driver-preparation.json', {
        'status': 'RESUME_DERIVED_CONTROLLER_PREPARED',
        'amendment_sha256': context.amendment_args.expected_amendment_sha256,
        'controller_sha256': sha(context.PRIVATE / 'controller.json'),
        'original_checkpoint_sha256': basis['checkpoint']['sha256'],
        'carried_public_artifacts': ['adoption', 'authorization_review', 'authorization_apply'],
        'new_model_reservations': 0, 'provider_accessed': False, 'service_action': False})
    return 0
