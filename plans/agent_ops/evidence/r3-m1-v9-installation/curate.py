"""Copy a fixed nonsecret installation evidence allowlist; never run a product."""
from pathlib import Path
import hashlib
import json
import re
import sys

REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
TEMP = Path('C:/Users/jpamb/AppData/Local/Temp')
TARGET = REPO / 'plans/agent_ops/evidence/r3-m1-v9-installation'
EXEC = TEMP / 'm1-v9-approved-execution'
BUNDLE = TEMP / 'm1-v9-preparation-t4xaqhca/draft'
DIAG = TEMP / 'm1-v9-requirements-diagnosis-sta2jii2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def verify(target):
    manifest = json.loads((target / 'artifact-manifest.json').read_bytes())
    for name, item in manifest['files'].items():
        data = (target / name).read_bytes()
        assert len(data) == item['bytes'] and sha(data) == item['sha256'], name
    assert {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()} == set(manifest['files']) | {'artifact-manifest.json'}
    old = (target / 'correction/original-approved-requirements.bin').read_bytes()
    new = (target / 'installation/products-requirements.txt').read_bytes()
    assert old.count(b'\r\n') == 3 and len(old) - len(new) == 3
    assert old.replace(b'\r\n', b'\n') == new and b'\r' not in new
    receipt = json.loads((target / 'installation/installation-result.json').read_bytes())
    assert receipt['payload_count'] == sum(p['files'] for p in receipt['packages'].values()) == 982
    assert receipt['pip_check']['returncode'] == receipt['pip_install']['returncode'] == 0
    for group, prefix in [('pip_install', 'product-install'), ('pip_check', 'pip-check')]:
        for stream in ['stdout', 'stderr']:
            assert sha((target / f'installation/{prefix}.{stream}.txt').read_bytes()) == receipt[group][stream + '_sha256']
    assert sha((target / 'installation/installation-reserved.json').read_bytes()) == receipt['reservation_sha256']
    assert json.loads((target / 'correction/timed_install-execute.stdout').read_bytes()) == receipt
    assert json.loads((target / 'first-refusal/timed_install-execute.stdout').read_bytes()) == {
        'status': 'REFUSED_OR_INCOMPLETE', 'code': 'REQUIREMENTS_CHANGED',
        'reservation_exists': False, 'retry_allowed': False}
    derived = json.loads((target / 'correction/authorization-derived.json').read_bytes())
    assert derived['direct_user_approval_for_corrected_hash'] is False
    assert sha((target / 'correction/authorization-derived.json').read_bytes()) == receipt['approval_sha256']
    assert sha((target / 'correction/proposal-v9-lf.json').read_bytes()) == receipt['proposal_sha256']
    print(json.dumps({'verified_files': len(manifest['files']), 'manifest_sha256': sha((target / 'artifact-manifest.json').read_bytes()), 'redactions': 0}))


def collect():
    assert not TARGET.exists(), 'Never overwrite evidence'
    mappings = []
    for name in ['timed_install-execute-process.json', 'timed_install-execute.stdout', 'timed_install-execute.stderr']:
        mappings.append((EXEC / name, 'first-refusal/' + name))
    for name in ['authorization-derived.json', 'correction.json', 'original-approved-requirements.bin', 'reference.json', 'timed_install-process.json', 'timed_install.stdout', 'timed_install.stderr', 'timed_install-execute-process.json', 'timed_install-execute.stdout', 'timed_install-execute.stderr']:
        mappings.append((EXEC / 'requirements-lf-correction' / name, 'correction/' + name))
    mappings.append((BUNDLE / 'm1-codex-campaign-proposal-v9-lf.json', 'correction/proposal-v9-lf.json'))
    for name in ['artifact-manifest.json', 'diagnose_requirements.py', 'diagnosis.json', 'expected-requirements-lf.txt', 'frozen-authorized-requirements-crlf.txt', 'install-source.txt', 'main-source.txt', 'verify_wheels-source.txt']:
        mappings.append((DIAG / name, 'diagnosis/' + name))
    for name in ['installation-result.json', 'installation-reserved.json', 'products-requirements.txt', 'installed-imports.stdout.txt', 'installed-imports.stderr.txt', 'pip-check.stdout.txt', 'pip-check.stderr.txt', 'product-install.stdout.txt', 'product-install.stderr.txt', 'timed_install.py']:
        mappings.append((BUNDLE / 'installation' / name, 'installation/' + name))
    payloads = [(source, name, source.read_bytes()) for source, name in mappings]
    secret_patterns = [rb'nxs_[A-Za-z0-9_-]{24,}', rb'nxobs_[A-Za-z0-9_-]{24,}', rb'(?i)Bearer [A-Za-z0-9_.-]{20,}']
    for source, name, data in payloads:
        assert not any(re.search(pattern, data) for pattern in secret_patterns), 'Possible secret in ' + name
    original = json.loads((BUNDLE / 'm1-codex-campaign-proposal-v9.json').read_bytes())
    corrected = json.loads((BUNDLE / 'm1-codex-campaign-proposal-v9-lf.json').read_bytes())
    expected = json.loads(json.dumps(original))
    for container, key in [(expected['base06_installation'], 'requirements_sha256'), (expected['execution_bundle']['files']['install_requirements'], 'sha256')]:
        container[key] = '4855ded4fc17b0fe38357463af53b97aaf0dfdddb8f6f71dddbec00c28b0b546'
    expected['input_representation_correction'] = corrected['input_representation_correction']
    assert expected == corrected, 'Unexpected scope delta'
    TARGET.mkdir(parents=True)
    provenance = {}
    for source, name, data in payloads:
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        provenance[name] = {'source_path': str(source), 'source_sha256': sha(data), 'transformation': 'none'}
    (TARGET / '.gitattributes').write_bytes(b'* -text -whitespace\n** -text -whitespace\n')
    (TARGET / 'curate.py').write_bytes(Path(__file__).read_bytes())
    receipt = json.loads((TARGET / 'installation/installation-result.json').read_bytes())
    qualification = {
        'status': 'INSTALLATION_VERIFIED_HISTORICAL_CHECKPOINT',
        'checkpoint_at_utc': receipt['timing']['verified_at_utc'],
        'not_live_campaign_state': True,
        'original_proposal_sha256': '9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279',
        'original_approval_sha256': '44dba586ced5eb3319bd4243a68ea3b2943b29cff1326f63fd8e942bf8ab8676',
        'derived_proposal_sha256': receipt['proposal_sha256'],
        'derived_authorization_sha256': receipt['approval_sha256'],
        'direct_user_approval_for_corrected_hash': False,
        'authorization_basis': 'Existing explicit authorization; exactly three CR bytes removed before installation. No new scope or user response claimed.',
        'proposal_semantic_delta_verified': ['base06_installation.requirements_sha256', 'execution_bundle.files.install_requirements.sha256', 'input_representation_correction (audit metadata only)'],
        'first_refusal': {'code': 'REQUIREMENTS_CHANGED', 'reservation_exists': False, 'subprocess_install_effect': False, 'source': 'first-refusal/timed_install-execute.stdout', 'effect_boundary_proof': 'diagnosis/diagnosis.json'},
        'validation': 'Actual corrected documents passed VALIDATED_NO_INSTALL before execution; no mocked validation or relaxed byte comparison.',
        'installation': {'effect_invocations': 1, 'status': receipt['status'], 'payload_count': receipt['payload_count'], 'package_files': {k: v['files'] for k, v in receipt['packages'].items()}, 'pip_install_returncode': 0, 'pip_check_returncode': 0, 'duration_ns': receipt['timing']['install_duration_ns'], 'reservation_sha256': receipt['reservation_sha256'], 'receipt_sha256': sha((TARGET / 'installation/installation-result.json').read_bytes()), 'provider_or_service_used_by_install': False, 'retry_allowed': False},
        'limits': ['This is installation evidence only; it does not assert the campaign is currently stopped or that later service/provider actions have not occurred.', 'BASE-06 requires the separately timed first useful canonical result; installation alone does not satisfy it.', 'No M1, task, scenario, invariant, milestone or acceptance criterion is promoted.', 'No wheels, venv, campaign database, private profile, credential, cookie or provider transcript is collected.'],
        'original_evidence': ['plans/agent_ops/evidence/r3-m1-v9-authorization/authorization.json', 'plans/agent_ops/evidence/r3-m1-v9-preparation/root-review.json'],
        'redactions': 0,
    }
    dump(TARGET / 'qualification.json', qualification)
    files = {}
    for path in sorted(TARGET.rglob('*')):
        if path.is_file():
            name = path.relative_to(TARGET).as_posix()
            data = path.read_bytes()
            files[name] = {'sha256': sha(data), 'bytes': len(data), **provenance.get(name, {'source': 'curation-created metadata'})}
    aggregate = sha(''.join(f'{name}\0{item["sha256"]}\n' for name, item in sorted(files.items())).encode())
    dump(TARGET / 'artifact-manifest.json', {'format': 'allowlisted-evidence-v1', 'status': qualification['status'], 'aggregate_algorithm': 'sha256(sorted(relative_path+NUL+file_sha256+LF), UTF-8)', 'aggregate_sha256': aggregate, 'redactions': 0, 'files': files})
    verify(TARGET)


if __name__ == '__main__':
    if sys.argv[1:] == ['--collect']:
        collect()
    else:
        verify(Path(__file__).resolve().parent)
