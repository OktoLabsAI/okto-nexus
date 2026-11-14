"""Synthetic pure gates and receipt transitions: never Popen, pip or network."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('timed_install', Path(__file__).with_name('timed_install.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PIN = {'script_sha256': '1' * 64, 'requirements_sha256': '2' * 64,
       'dependency_manifest_sha256': '3' * 64}
P_HASH, A_HASH = 'a' * 64, 'b' * 64


@pytest.fixture(autouse=True)
def never_spawn(monkeypatch):
    monkeypatch.setattr(module, 'FINAL_PINS_BOUND', True)
    def forbidden(*args, **kwargs):
        pytest.fail('No subprocess may run in these synthetic tests')
    monkeypatch.setattr(module.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(module.subprocess, 'run', forbidden)


def documents():
    proposal = {'format': 'okto.m1.codex-real-campaign-proposal', 'revision': 11,
        'paths': {'campaign_root': str(module.CAMPAIGN)},
        'controller_preparation': {'policy': copy.deepcopy(module.POLICY), 'ancestry': copy.deepcopy(module.ANCESTRY)},
        'base06_installation': {**PIN, 'python': str(module.PYTHON), 'python_prefix': str(module.PREFIX),
            'script': str(module.SCRIPT), 'result': str(module.RESULT), 'reservation': str(module.RESERVATION)},
        'package_pins': {'python': str(module.PYTHON), 'python_prefix': str(module.PREFIX),
            'packages': {name: {**pin, 'package': str(module.SITE / name)} for name, pin in module.WHEELS.items()}}}
    approval = {'status': 'USER_APPROVED', 'proposal_revision': 11, 'proposal_sha256': P_HASH,
        'campaign_root': str(module.CAMPAIGN), 'policy': copy.deepcopy(module.POLICY),
        'ancestry': copy.deepcopy(module.ANCESTRY), 'user_quote': 'SYNTHETIC IN-MEMORY GATE TEST, NOT REAL AUTHORIZATION'}
    return proposal, approval


def test_exact_v11_receipt_gate_does_not_install():
    proposal, approval = documents()
    assert module.validate_documents(proposal, approval, P_HASH, A_HASH, PIN) == {
        'proposal_sha256': P_HASH, 'approval_sha256': A_HASH, 'proposal_revision': 11,
        'campaign_root': str(module.CAMPAIGN)}


@pytest.mark.parametrize('change', [
    'v7', 'bool_revision', 'no_approval', 'wrong_hash', 'wrong_root',
    'policy_limit', 'policy_bool', 'ancestry', 'no_quote', 'python', 'script',
    'requirements', 'wheel', 'count', 'missing_product',
])
def test_exact_scope_and_typed_policy_fail_before_any_effect(change):
    proposal, approval = documents()
    if change == 'v7':
        approval['proposal_revision'] = 7
    elif change == 'bool_revision':
        proposal['revision'] = True
    elif change == 'no_approval':
        approval['status'] = 'PREPARED'
    elif change == 'wrong_hash':
        approval['proposal_sha256'] = 'c' * 64
    elif change == 'wrong_root':
        approval['campaign_root'] = str(module.CAMPAIGN.parent / 'other')
    elif change == 'policy_limit':
        approval['policy']['max_new_admissions'] = 7
    elif change == 'policy_bool':
        approval['policy']['carry_in_admissions'] = True
    elif change == 'ancestry':
        approval['ancestry']['predecessor_faults'] = []
    elif change == 'no_quote':
        approval['user_quote'] = ''
    elif change == 'python':
        proposal['base06_installation']['python'] = str(module.BASE_PYTHON)
    elif change == 'script':
        proposal['base06_installation']['script_sha256'] = 'f' * 64
    elif change == 'requirements':
        proposal['base06_installation']['requirements_sha256'] = 'f' * 64
    elif change == 'wheel':
        proposal['package_pins']['packages']['okto_nexus']['sha256'] = 'f' * 64
    elif change == 'count':
        proposal['package_pins']['packages']['okto_nexus']['files'] = True
    elif change == 'missing_product':
        proposal['package_pins']['packages'].pop('nexus_connector_core')
    with pytest.raises(module.GateError):
        module.validate_documents(proposal, approval, P_HASH, A_HASH, PIN)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'])
def test_ambiguous_json_is_refused(raw):
    with pytest.raises(module.GateError):
        module.strict_json(raw)


def test_pinned_document_rejects_different_bytes_and_oversize(tmp_path):
    path = tmp_path / 'synthetic.json'
    raw = b'{"fixture":"synthetic"}'
    path.write_bytes(raw)
    assert module.pinned_document(path, module.sha(raw)) == {'fixture': 'synthetic'}
    with pytest.raises(module.GateError, match='HASH_MISMATCH'):
        module.pinned_document(path, 'f' * 64)
    with pytest.raises(module.GateError, match='TOO_LARGE'):
        module.pinned_document(path, module.sha(raw), limit=5)


def test_exclusive_reservation_linearizes_concurrent_callers(tmp_path):
    path = tmp_path / 'synthetic-reservation.json'
    def reserve(index):
        try:
            return module.write_exclusive(path, {'synthetic_owner': index})
        except FileExistsError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (1, 2)))
    assert sum(value is not None for value in results) == 1
    assert module.sha(path.read_bytes()) in results


@pytest.mark.parametrize('state', ['RESERVATION', 'RESULT', 'UNKNOWN'])
def test_any_prior_reservation_or_unknown_blocks_retry_before_documents(tmp_path, monkeypatch, state):
    for name in ('RESERVATION', 'RESULT', 'UNKNOWN'):
        monkeypatch.setattr(module, name, tmp_path / (name + '.json'))
    getattr(module, state).write_bytes(b'partial or unknown')
    with pytest.raises(module.GateError, match='ALREADY_RESERVED'):
        module.install(SimpleNamespace(execute=True))


def test_unknown_after_reserved_install_never_reexecutes(tmp_path, monkeypatch):
    proposal, approval = documents()
    for name in ('RESERVATION', 'RESULT', 'UNKNOWN'):
        monkeypatch.setattr(module, name, tmp_path / (name + '.json'))
    # Pure valid-document gate was exercised above; this case isolates the
    # durable transition after a hypothetical approved install was reserved.
    monkeypatch.setattr(module, 'pinned_document', lambda path, *a, **kw: proposal if path == 'proposal' else approval)
    monkeypatch.setattr(module, 'artifact_pins', lambda: PIN)
    monkeypatch.setattr(module, 'validate_documents', lambda *args: {'proposal_sha256': P_HASH, 'approval_sha256': A_HASH})
    monkeypatch.setattr(module, 'verify_dependencies', lambda: None)
    monkeypatch.setattr(module, 'verify_wheels', lambda: None)
    calls = []
    def failure(*args, **kwargs):
        calls.append(args)
        raise OSError('synthetic failure, no process launched')
    monkeypatch.setattr(module, 'run_process', failure)
    args = SimpleNamespace(proposal='proposal', expected_proposal_sha256=P_HASH,
                           approval_path='approval', approval_sha256=A_HASH, execute=True)
    with pytest.raises(OSError):
        module.install(args)
    assert module.RESERVATION.exists() and module.UNKNOWN.exists() and not module.RESULT.exists()
    assert json.loads(module.UNKNOWN.read_text())['possible_effect'] is True
    with pytest.raises(module.GateError, match='ALREADY_RESERVED'):
        module.install(args)
    assert len(calls) == 1


def test_default_mode_is_validation_only(monkeypatch, capsys):
    captured = []
    monkeypatch.setattr(module, 'install', lambda args: captured.append(args.execute) or {'status': 'SYNTHETIC'})
    assert module.main(['--proposal', 'synthetic', '--expected-proposal-sha256', P_HASH,
                        '--approval-path', 'synthetic', '--approval-sha256', A_HASH]) == 0
    assert captured == [False]
    assert 'SYNTHETIC' in capsys.readouterr().out


def test_previous_v9_approval_does_not_authorize_successor():
    proposal, approval = documents()
    approval['proposal_revision'] = 9
    with pytest.raises(module.GateError, match='APPROVAL_REQUIRED'):
        module.validate_documents(proposal, approval, P_HASH, A_HASH, PIN)


def test_requirements_lf_exact_bytes_and_crlf_refusal(tmp_path, monkeypatch):
    wheel = tmp_path / 'synthetic.whl'
    wheel.write_bytes(b'synthetic archive marker; never installed')
    requirements = tmp_path / 'products-requirements.txt'
    digest = module.sha(wheel.read_bytes())
    monkeypatch.setattr(module, 'WHEELS', {'synthetic': {'wheel': str(wheel), 'sha256': digest}})
    monkeypatch.setattr(module, 'REQUIREMENTS', requirements)
    raw = (wheel.as_uri() + ' --hash=sha256:' + digest + '\n').encode('utf-8')
    requirements.write_bytes(raw)
    module.verify_wheels()
    requirements.write_bytes(raw.replace(b'\n', b'\r\n'))
    with pytest.raises(module.GateError, match='REQUIREMENTS_CHANGED'):
        module.verify_wheels()


def test_wheel_count_comes_from_pinned_payload_manifest():
    manifest = json.loads((Path(__file__).resolve().parent.parent / 'wheel-payload-pins.json').read_bytes())
    assert module.EXPECTED_PAYLOAD_COUNT == sum(x['files'] for x in manifest['packages'].values())
    assert module.EXPECTED_PAYLOAD_COUNT == len(manifest['files'])
    assert module.WHEELS == manifest['packages']
