"""Offline fixtures only: no imports of product, Scheduler, provider or live DB."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import resume_context as ctx
import resume_entry as entry
import invoke_resume as invoke


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return {'path': str(path), 'sha256': ctx.sha(path)}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    root = tmp_path / 'own'
    control = root / 'successor14'
    here = control / 'resume-request01'
    here.mkdir(parents=True)
    for mod in (ctx, invoke):
        monkeypatch.setattr(mod, 'HERE', here)
    monkeypatch.setattr(ctx, 'CONTROL', control)
    monkeypatch.setattr(ctx, 'ROOT', root)
    monkeypatch.setattr(ctx, '_context', None)
    public, private = here / 'public', here / 'private'
    common = SimpleNamespace()
    common.owned_path = lambda path, own: Path(path).resolve()
    common.sha = ctx.sha
    common.tags = lambda context: {'campaign_revision': 14, 'control_root': str(context.CONTROL)}
    common.reserve = lambda path, value: Path(path).open('x', encoding='utf-8').write(json.dumps(value))
    common.FINITE_CHOICES = {'lifecycle': [('initialize',), ('nexus', 'install'), ('nexus', 'start'), ('nexus', 'stop'), ('nexus', 'uninstall')],
                             'work': [('local', 'useful'), ('local', 'continuation')],
                             'remote_setup': [('transfer',)], 'operator_bootstrap': [('once',)],
                             'plan': [('remote_plan',)]}
    runtime = here / 'runtime-private'
    def private_outputs():
        runtime.mkdir(exist_ok=True)
        return runtime
    common.private_outputs = private_outputs
    origcontext = put(control / 'original-context.py', {})
    origcommon = put(control / 'original-common.py', {})
    lifecycle = put(control / 'original-lifecycle.py', {})
    proposal = {'execution_bundle': {'files': {'context': origcontext, 'root_driver_common': origcommon,
                                             'lifecycle': lifecycle}},
                'controller_preparation': {'policy': {'revision': 14}},
                'package_pins': {'python': 'own-python'}}
    proposal_pin = put(control / 'proposal.json', proposal)
    base = SimpleNamespace(P=proposal, C={'steps': [{'component':'nexus','action':'start','argv':['own-python','-I','-B','-m','fixture','start']}]}, ROOT=root, CONTROL=control,
        args=SimpleNamespace(expected_proposal_sha256=proposal_pin['sha256'], approval_path='original-receipt', approval_sha256='same-receipt-sha'),
        env=lambda: {'OWN': 'ENV'})
    calls = []
    original = SimpleNamespace(load=lambda: calls.append(list(sys.argv)) or base)
    def module(name, path):
        return original if name == 'campaign_context' else common
    monkeypatch.setattr(ctx, 'module', module)
    sources = {key: put(here / filename, {}) for key, filename in
        [('context','resume_context.py'), ('entry','resume_entry.py'), ('invoke','invoke_resume.py'), ('work','resume_work.py')]}
    sources['resumed_controller'] = put(tmp_path / 'candidate/resumed_controller.py', {})
    checkpoint = put(control / 'private/controller.json', {'original': True})
    closure = put(control / 'public/closure.json', {'controller_checkpoint_sha256': checkpoint['sha256'],
        'closed_without_force': True, 'all_temporary_tasks_absent': True,
        'cumulative_reserved_admissions': 10, 'cumulative_minimum_observed_tokens': 134199})
    amendment = {'format': 'okto.m1.v14.resume-request01', 'resume_root': str(here), 'control_root': str(control),
        'policy': proposal['controller_preparation']['policy'], 'sources': sources,
        'basis': {'checkpoint': checkpoint, 'closure': closure},
        'original': {'proposal': proposal_pin['path'], 'proposal_sha256': proposal_pin['sha256'],
                     'approval': 'original-receipt', 'approval_sha256': 'same-receipt-sha'}}
    amendment_pin = put(here / 'amendment.json', amendment)
    args = SimpleNamespace(amendment=amendment_pin['path'], expected_amendment_sha256=amendment_pin['sha256'])
    return SimpleNamespace(root=root, control=control, here=here, public=public, private=private,
        common=common, args=args, amendment=amendment, calls=calls, original=original)


def test_gate_keeps_original_authority_and_redirects_only_evidence(fake):
    value = ctx.gate(fake.args)
    assert value.CONTROL == fake.control and value.ROOT == fake.root
    assert value.PUBLIC == fake.public and value.PRIVATE == fake.private
    assert value.P['controller_preparation']['policy'] == {'revision': 14}
    assert len(fake.calls) == 1 and 'original-receipt' in fake.calls[0]
    assert fake.original.load() is value and fake.common.gate(fake.args) is value
    assert fake.common.HERE == fake.here
    assert value.stop_argv('nexus')[-3:] == ['lifecycle','nexus','stop']
    assert value.stop_argv('nexus')[1:3] == ['-X','utf8']
    assert value.C['steps'][0]['argv'][1:3] == ['-X','utf8']
    assert value.base.C['steps'][0]['argv'][1:3] == ['-I','-B']
    assert str(fake.here / 'resume_entry.py') in value.stop_argv('nexus')
    assert not fake.public.exists() and not fake.private.exists()


def test_bad_amendment_refused_before_original_gate(fake):
    fake.args.expected_amendment_sha256 = '0' * 64
    with pytest.raises(RuntimeError, match='AMENDMENT_CHANGED'):
        ctx.gate(fake.args)
    assert fake.calls == []


def test_missing_candidate_pin_refused_before_original_gate(fake):
    Path(fake.amendment['sources']['resumed_controller']['path']).with_name('unreviewed.py').write_text('')
    with pytest.raises(RuntimeError, match='UNPINNED_CONTROLLER_SOURCE'):
        ctx.gate(fake.args)
    assert fake.calls == []


def test_closed_resume_cannot_reenter_even_cached_context(fake):
    ctx.gate(fake.args)
    put(fake.public / 'closure.json', {})
    with pytest.raises(RuntimeError, match='RESUME_ALREADY_CLOSED'):
        ctx.gate(fake.args)


def test_controller_passes_derived_path_and_original_receipt(fake, monkeypatch):
    value = ctx.gate(fake.args)
    observed = []
    monkeypatch.setitem(sys.modules, 'resumed_controller', SimpleNamespace(ResumedController=lambda *a, **kw: observed.append((a,kw))))
    value.controller()
    args, kwargs = observed[0]
    assert args == (fake.private / 'controller.json', fake.root)
    assert kwargs['original_control_root'] == fake.control
    assert kwargs['first_dispatch_receipt'] == fake.private / 'first-dispatch.json'
    assert kwargs['approval_path'] == 'original-receipt'
    with pytest.raises(RuntimeError, match='DERIVED_CONTROLLER_MUST_BE_PREPARED'):
        value.controller(create=True)


def prepared(fake):
    value = ctx.gate(fake.args)
    put(fake.public / 'root-driver-preparation.json', {})
    return value


def test_dispatch_reserves_before_spawn_and_retains_exit(fake):
    value = prepared(fake)
    calls = []
    def popen(argv, **kwargs):
        directory = kwargs['cwd']
        assert (directory / 'work-local-useful.reserved.json').is_file()
        assert argv[-3:] == ['work','local','useful']
        assert str(fake.here / 'resume_entry.py') in argv
        calls.append(argv)
        return SimpleNamespace(pid=123, wait=lambda: 7)
    result = invoke.dispatch(value, 'work', ['local','useful'], popen=popen)
    assert result['returncode'] == 7 and result['wrapper_exit_confirmed'] is True
    with pytest.raises(FileExistsError):
        invoke.dispatch(value, 'work', ['local','useful'], popen=popen)
    assert len(calls) == 1


def test_spawn_failure_consumes_selection(fake):
    value = prepared(fake)
    calls = []
    def failed(*args, **kwargs):
        calls.append(True)
        raise OSError('fixture spawn failure')
    with pytest.raises(OSError):
        invoke.dispatch(value, 'lifecycle', ['nexus','install'], popen=failed)
    with pytest.raises(FileExistsError):
        invoke.dispatch(value, 'lifecycle', ['nexus','install'], popen=failed)
    assert len(calls) == 1


@pytest.mark.parametrize('mode,selection', [('lifecycle',['initialize']), ('lifecycle',['nexus','force']), ('setup',['local']),
    ('work',['connector','useful']), ('remote_setup',['transfer']), ('operator_bootstrap',['once']), ('plan',['remote_plan']), ('lifecycle',['connector','install'])])
def test_out_of_scope_selection_never_spawns(fake, mode, selection):
    value = prepared(fake)
    with pytest.raises(RuntimeError, match='FINITE_SELECTION_INVALID'):
        invoke.dispatch(value, mode, selection, popen=lambda *a, **kw: pytest.fail('unexpected spawn'))


def test_lifecycle_runs_pinned_original_with_resume_context(fake):
    value = prepared(fake)
    seen=[]
    def run(path, run_name):
        assert fake.original.load() is value
        assert value.remaining == ['nexus','stop']
        seen.append((path,run_name))
        raise SystemExit(3)
    assert entry.execute(value,'lifecycle',['nexus','stop'],run=run) == 3
    assert seen[0][0] == value.P['execution_bundle']['files']['lifecycle']['path']


def test_work_delta_is_exact_and_old_decision_does_not_dispatch():
    here = Path(__file__).parent
    old=(here.parent / 'draft/m1_v14_work.py').read_text(encoding='utf-8')
    new=(here / 'resume_work.py').read_text(encoding='utf-8')
    expected=old.replace("decision_path=X.PRIVATE/(approval+'-reviewed-decision.json')", "decision_path=X.PRIVATE/'native-decision.json'")
    expected=expected.replace("    assert decision['approval_id']==approval and decision['review_revision']==revision", "    if decision.get('approval_id')!=approval or decision.get('review_revision')!=revision:return")
    expected=expected.replace('        time.sleep(.2)\n    # Drain before', '        time.sleep(max(0,.2-(time.monotonic()-now)))\n    # Drain before')
    expected=expected.replace("        require(hashlib.sha256(Path(predecessor_work['path']).read_bytes()).hexdigest()==authorization_basis['work_checkpoint_sha256'],\n            'PREDECESSOR_WORK_CHANGED_BEFORE_NEW_SESSION')", "        require(X.validate_resumed_work(flow.document,text,document_revision),\n            'RESUMED_WORK_CHECKPOINT_REQUIRED')")
    assert new == expected


def test_resume_work_pin_binds_same_pending_intent_and_prompt(fake):
    value = ctx.gate(fake.args)
    expected = {'session_id': 'old-closed', 'client_intent_id': 'm1v14-local-work-01',
        'request_hash': 'same-hash', 'intent': 'runtime.start', 'state': 'resolve_submitted',
        'has_text': True, 'action': 'send', 'request_context': {'client_intent_id': 'm1v14-local-work-01', 'new_session': True}}
    document = {'session_id': 'old-closed', 'work': {k:v for k,v in expected.items() if k != 'session_id'}}
    value.amendment['initial_work_checkpoint'] = put(fake.root / 'owned-work.json', document)
    value.amendment['initial_work_selection'] = expected
    calls = []
    def revision(request):
        calls.append(request)
        return 'same-hash' if request['text'] == 'same text' else 'other-hash'
    assert value.validate_resumed_work(document, 'same text', revision)
    assert calls == [dict(expected['request_context'], text='same text')]
    with pytest.raises(RuntimeError, match='RESUMED_PROMPT_CHANGED'):
        value.validate_resumed_work(document, 'different text', revision)
    changed = json.loads(json.dumps(document)); changed['work']['client_intent_id'] = 'other'
    with pytest.raises(RuntimeError, match='WORK_DOCUMENT_CHANGED'):
        value.validate_resumed_work(changed, 'same text', revision)
    # Canonical writes after the first dispatch must not invalidate unrelated
    # control/cleanup gates; only initial resumption uses the live work pin.
    put(fake.root / 'owned-work.json', changed)
    assert ctx.gate(fake.args) is value


def test_explicit_utf8_survives_isolated_python_json_roundtrip():
    script="import json; print(json.dumps({'display_name':chr(0x2014)},ensure_ascii=False))"
    argv=ctx.python_utf8([sys.executable,'-I','-B','-c',script],sys.executable)
    environment={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP')}
    environment['PYTHONUTF8']='0'  # ignored by -I; explicit flag is authoritative
    result=subprocess.run(argv,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=15)
    assert json.loads(result.stdout)=={'display_name':chr(0x2014)}
    assert bytes.fromhex('e28094') in result.stdout
    with pytest.raises(RuntimeError,match='PYTHON_INTERPRETER_CHANGED'):
        ctx.python_utf8(['codex.exe','app-server'],sys.executable)
