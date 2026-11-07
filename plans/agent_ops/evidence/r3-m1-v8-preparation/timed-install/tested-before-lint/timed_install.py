"""Single reserved offline product installation for the exact proposed M1 v8.

Preparation is not authorization. The normal mode only validates. --execute
additionally requires the exact externally pinned user-approval receipt. Any
reservation, including an interrupted/uncertain one, prevents another install.
Only stdlib is used by this controller. No product CLI, service or provider is
invoked. This measures the product installation boundary, not dependency setup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe')
PREFIX = ROOT / 'venv'
PYTHON = PREFIX / 'Scripts/python.exe'
BASE_PYTHON = Path('C:/Python313/python.exe')
SITE = PREFIX / 'Lib/site-packages'
SCRIPT = ROOT / 'timed_install.py'
REQUIREMENTS = ROOT / 'products-requirements.txt'
RESERVATION = ROOT / 'installation-reserved.json'
RESULT = ROOT / 'installation-result.json'
UNKNOWN = ROOT / 'installation-unknown.json'
CAMPAIGN = Path('C:/Users/jpamb/AppData/Local/Temp/m1-fresh-v8-pg0b6zbf/campaign')
POLICY = {'revision': 8, 'carry_in_admissions': 2, 'carry_in_tokens': 45843,
          'max_cumulative_admissions': 8, 'max_new_admissions': 6,
          'preventive_cumulative_tokens': 200000, 'operational_tolerance': 700000,
          'deadline_seconds': 120}
ANCESTRY = {'closure_sha256': '8193dc80dba36296666223a1e29e4170ee233e319b46021037854b8f1dfbf67b',
            'checkpoint_sha256': '78026c0b5c6c21524a7d3f41c1e3183c9ec685da313365b6faeaa2f4e0c3db9e',
            'predecessor_faults': ['CAMPAIGN_RUNNER_EXCEPTION']}
WHEELS = {
    'okto_nexus': {
        'wheel': 'C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc/wheels/okto_nexus-0.3.3-py3-none-any.whl',
        'sha256': 'fdb8f37866f5332244a6916d6e6eaac433cd317d4ed2792a81bd4a3f426b49c2', 'files': 691},
    'okto_nexus_connector': {
        'wheel': 'C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl',
        'sha256': '73f1a3ba6daf1a4db6f98a9eaf7badaed0d32b151a30b4c0c6a0cf66c2eae1b5', 'files': 124},
    'nexus_connector_core': {
        'wheel': 'C:/Users/jpamb/AppData/Local/Temp/core-dx43-observation-du1arc40/wheel/okto_nexus_connector_core-0.0.14-py3-none-any.whl',
        'sha256': '609e0fbbb20855c6b788d2523b0aeb6cdfbf4b3f5c9792c9e4a080284729c9dd', 'files': 167},
}
PRODUCT_DISTS = ('okto-nexus', 'okto-nexus-connector', 'okto-nexus-connector-core')


class GateError(RuntimeError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def fail_unless(condition, code):
    if not condition:
        raise GateError(code)


def pairs(items):
    result = {}
    for key, value in items:
        fail_unless(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def strict_json(raw):
    def invalid_constant(_):
        raise GateError('NONFINITE_JSON')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise GateError('INVALID_JSON') from None


def pinned_document(path, digest, *, limit=2 * 1024 * 1024):
    fail_unless(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'INVALID_HASH')
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    fail_unless(len(raw) <= limit, 'DOCUMENT_TOO_LARGE')
    fail_unless(sha(raw) == digest, 'DOCUMENT_HASH_MISMATCH')
    document = strict_json(raw)
    fail_unless(type(document) is dict, 'DOCUMENT_OBJECT_REQUIRED')
    return document


def same_path(value, expected):
    return type(value) is str and Path(value).is_absolute() and Path(value) == expected


def validate_documents(proposal, approval, proposal_hash, approval_hash, artifact_pins):
    """Pure typed gate: current v8 proposal plus a separately pinned receipt."""
    fail_unless(type(proposal) is dict and type(approval) is dict, 'DOCUMENT_OBJECT_REQUIRED')
    fail_unless(proposal.get('format') == 'okto.m1.codex-real-campaign-proposal'
                and type(proposal.get('revision')) is int and proposal['revision'] == 8,
                'PROPOSAL_REVISION_MISMATCH')
    fail_unless(approval.get('status') == 'USER_APPROVED'
                and type(approval.get('proposal_revision')) is int
                and approval['proposal_revision'] == 8
                and approval.get('proposal_sha256') == proposal_hash, 'APPROVAL_REQUIRED')
    fail_unless(type(proposal_hash) is str and re.fullmatch('[0-9a-f]{64}', proposal_hash)
                and type(approval_hash) is str and re.fullmatch('[0-9a-f]{64}', approval_hash),
                'INVALID_HASH')
    fail_unless(same_path(proposal.get('paths', {}).get('campaign_root'), CAMPAIGN)
                and same_path(approval.get('campaign_root'), CAMPAIGN), 'CAMPAIGN_MISMATCH')
    controller = proposal.get('controller_preparation', {})
    fail_unless(canonical(controller.get('policy')) == canonical(POLICY)
                and canonical(approval.get('policy')) == canonical(POLICY), 'POLICY_MISMATCH')
    fail_unless(canonical(controller.get('ancestry')) == canonical(ANCESTRY)
                and canonical(approval.get('ancestry')) == canonical(ANCESTRY), 'ANCESTRY_MISMATCH')
    quote = approval.get('user_quote')
    fail_unless(type(quote) is str and bool(quote.strip()) and len(quote) <= 16384, 'USER_QUOTE_REQUIRED')
    install = proposal.get('base06_installation')
    fail_unless(type(install) is dict, 'INSTALLATION_NOT_REVIEWED')
    expected_paths = {'python': PYTHON, 'python_prefix': PREFIX, 'script': SCRIPT,
                      'result': RESULT, 'reservation': RESERVATION}
    for key, expected in expected_paths.items():
        fail_unless(same_path(install.get(key), expected), 'INSTALLATION_TARGET_MISMATCH')
    for key in ('script_sha256', 'requirements_sha256', 'dependency_manifest_sha256'):
        fail_unless(install.get(key) == artifact_pins[key], 'INSTALLER_ARTIFACT_MISMATCH')
    package_pins = proposal.get('package_pins', {})
    fail_unless(same_path(package_pins.get('python'), PYTHON)
                and same_path(package_pins.get('python_prefix'), PREFIX), 'PRODUCT_TARGET_MISMATCH')
    packages = package_pins.get('packages', {})
    fail_unless(type(packages) is dict and set(packages) == set(WHEELS), 'PACKAGE_SET_MISMATCH')
    for module, expected in WHEELS.items():
        actual = packages[module]
        fail_unless(type(actual) is dict and actual.get('sha256') == expected['sha256']
                    and type(actual.get('files')) is int and actual['files'] == expected['files']
                    and same_path(actual.get('wheel'), Path(expected['wheel']))
                    and same_path(actual.get('package'), SITE / module), 'PACKAGE_PIN_MISMATCH')
    return {'proposal_sha256': proposal_hash, 'approval_sha256': approval_hash,
            'proposal_revision': 8, 'campaign_root': str(CAMPAIGN)}


def write_exclusive(path, document):
    """An incomplete write is retained and also blocks a repeated install."""
    raw = (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha(raw)


def require_unreserved():
    fail_unless(not any(path.exists() for path in (RESERVATION, RESULT, UNKNOWN)), 'INSTALL_ALREADY_RESERVED')


def artifact_pins():
    fail_unless(Path(__file__).resolve() == SCRIPT, 'INSTALLER_PATH_MISMATCH')
    return {'script_sha256': sha(SCRIPT.read_bytes()),
            'requirements_sha256': sha(REQUIREMENTS.read_bytes()),
            'dependency_manifest_sha256': sha((ROOT / 'dependency-manifest.json').read_bytes())}


def environment():
    prepared = strict_json((ROOT / 'environment.json').read_bytes())
    report = strict_json((ROOT / 'dependency-preparation.json').read_bytes())
    fail_unless(report['environment_sha256'] == sha((ROOT / 'environment.json').read_bytes()),
                'ENVIRONMENT_CHANGED')
    # Launch the actual Python executable, not the Windows venv redirector.
    # CPython's launcher variable selects the same disposable virtualenv. A
    # benign preflight pins prefix and confirms Popen.pid == child PID. Thus a
    # timeout contains only our exact pip child, never a PID selected by name.
    prepared['__PYVENV_LAUNCHER__'] = str(PYTHON)
    return prepared


def run_process(argv, label, *, timeout=180):
    output = ROOT / (label + '.stdout.txt')
    error = ROOT / (label + '.stderr.txt')
    with output.open('xb') as stdout, error.open('xb') as stderr:
        completed = subprocess.run(argv, cwd=ROOT / 'isolated', env=environment(),
            stdout=stdout, stderr=stderr, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'returncode': completed.returncode,
            'stdout_sha256': sha(output.read_bytes()), 'stderr_sha256': sha(error.read_bytes())}


def verify_dependencies():
    report = strict_json((ROOT / 'dependency-preparation.json').read_bytes())
    fail_unless(report.get('status') == 'DEPENDENCIES_ONLY_READY', 'DEPENDENCIES_NOT_READY')
    manifest = pinned_document(ROOT / 'dependency-manifest.json', report['dependency_manifest_sha256'], limit=8 * 1024 * 1024)
    fail_unless(same_path(manifest.get('destination'), SITE), 'DEPENDENCY_TARGET_MISMATCH')
    expected = manifest['files']
    actual = {path.relative_to(SITE).as_posix(): sha(path.read_bytes())
              for path in SITE.rglob('*') if path.is_file()
              and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    fail_unless(actual == expected, 'DEPENDENCY_BYTES_CHANGED_OR_PRODUCT_PRESENT')
    probe = strict_json((ROOT / 'direct-interpreter-final.json').read_bytes())
    fail_unless(probe['status'] == 'PASS' and probe['launcher_pid_matches_child'] is True,
                'DIRECT_INTERPRETER_UNCONFIRMED')
    fail_unless(sha(BASE_PYTHON.read_bytes()) == probe['base_executable_sha256']
                and sha(PYTHON.read_bytes()) == probe['venv_python_sha256'], 'PYTHON_BYTES_CHANGED')


def verify_wheels():
    for pin in WHEELS.values():
        fail_unless(sha(Path(pin['wheel']).read_bytes()) == pin['sha256'], 'WHEEL_BYTES_CHANGED')
    expected = ''.join(Path(pin['wheel']).as_uri() + ' --hash=sha256:' + pin['sha256'] + '\n'
                       for pin in WHEELS.values())
    fail_unless(REQUIREMENTS.read_bytes() == expected.encode('utf-8'), 'REQUIREMENTS_CHANGED')


def installed_payloads():
    packages = {}
    total = 0
    for module, pin in WHEELS.items():
        with zipfile.ZipFile(pin['wheel']) as wheel:
            expected = {name: sha(wheel.read(name)) for name in wheel.namelist()
                        if name.startswith(module + '/') and not name.endswith('/')}
        found = {path.relative_to(SITE).as_posix(): sha(path.read_bytes())
                 for path in (SITE / module).rglob('*') if path.is_file()
                 and '__pycache__' not in path.parts and path.suffix != '.pyc'}
        fail_unless(expected == found and len(found) == pin['files'], 'INSTALLED_PAYLOAD_MISMATCH')
        packages[module] = {**pin, 'package': str(SITE / module)}
        total += len(found)
    fail_unless(total == 982, 'PAYLOAD_COUNT_MISMATCH')
    return packages


def install(args):
    require_unreserved()
    proposal = pinned_document(args.proposal, args.expected_proposal_sha256)
    approval = pinned_document(args.approval_path, args.approval_sha256, limit=65536)
    pins = artifact_pins()
    authorization = validate_documents(proposal, approval, args.expected_proposal_sha256,
                                       args.approval_sha256, pins)
    verify_dependencies()
    verify_wheels()
    if not args.execute:
        return {'status': 'VALIDATED_NO_INSTALL', **authorization, 'products_installed': False}
    reservation = {'format': 'okto.base06.installation-reservation', 'revision': 1,
                   'status': 'RESERVED_INCOMPLETE', **authorization, 'artifact_pins': pins,
                   'python': str(PYTHON), 'python_prefix': str(PREFIX),
                   'reserved_at_utc': utc_now(), 'possible_effect': True,
                   'retry_allowed': False}
    # O_EXCL is the linearization point: two callers cannot both install.
    reservation_hash = write_exclusive(RESERVATION, reservation)
    timing = {}
    phase = 'preinstall_recheck'
    try:
        verify_dependencies()
        verify_wheels()
        phase = 'pip_install'
        timing.update(install_started_at_utc=utc_now(), install_started_monotonic_ns=time.monotonic_ns())
        # Exact wheel requirements carry hashes, so pip rechecks the bytes it
        # consumes rather than relying only on the earlier filesystem check.
        pip = run_process([str(BASE_PYTHON), '-I', '-B', '-X', 'utf8', '-m', 'pip',
            '--isolated', '--disable-pip-version-check', '--no-input', 'install',
            '--no-index', '--no-deps', '--no-cache-dir', '--no-compile', '--require-hashes',
            '-r', str(REQUIREMENTS)], 'product-install')
        timing.update(install_completed_at_utc=utc_now(), install_completed_monotonic_ns=time.monotonic_ns())
        timing['install_duration_ns'] = timing['install_completed_monotonic_ns'] - timing['install_started_monotonic_ns']
        fail_unless(pip['returncode'] == 0, 'PIP_INSTALL_FAILED')
        phase = 'package_verification'
        packages = installed_payloads()
        probe_code = '''import importlib, json, sys
from pathlib import Path
names = ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core')
expected = Path(sys.argv[1])
assert Path(sys.prefix) == expected
origins = {name: importlib.import_module(name).__file__ for name in names}
assert all(Path(origin).is_relative_to(expected / 'Lib/site-packages') for origin in origins.values())
print(json.dumps(origins))
'''
        probe = run_process([str(BASE_PYTHON), '-I', '-B', '-X', 'utf8', '-c', probe_code, str(PREFIX)], 'installed-imports', timeout=30)
        fail_unless(probe['returncode'] == 0, 'INSTALLED_IMPORT_PREFIX_FAILED')
        imports = strict_json((ROOT / 'installed-imports.stdout.txt').read_bytes())
        phase = 'pip_check'
        check = run_process([str(BASE_PYTHON), '-I', '-B', '-X', 'utf8', '-m', 'pip',
                             '--isolated', '--disable-pip-version-check', 'check'], 'pip-check', timeout=30)
        fail_unless(check['returncode'] == 0, 'PIP_CHECK_FAILED')
        timing.update(verified_at_utc=utc_now(), verified_monotonic_ns=time.monotonic_ns())
        result = {'format': 'okto.base06.installation', 'revision': 1, 'status': 'INSTALLED_VERIFIED',
                  **authorization, 'python': str(PYTHON), 'python_prefix': str(PREFIX),
                  'payload_count': 982, 'packages': packages, 'imports': imports, 'pip_check': check,
                  'pip_install': pip, 'timing': timing, 'reservation_sha256': reservation_hash,
                  'provider_or_service_used': False, 'retry_allowed': False,
                  'limits': 'Product install only: dependency preparation/download/build and waiting for user approval are excluded. First useful canonical result must be timed separately on the same boot/campaign; this receipt alone does not satisfy BASE-06.'}
        write_exclusive(RESULT, result)
        return result
    except BaseException as error:
        # No rollback/uninstall/retry. Even if publishing this diagnostic fails,
        # the exclusive reservation remains and blocks any second installation.
        try:
            write_exclusive(UNKNOWN, {'format': 'okto.base06.installation-unknown', 'revision': 1,
                'status': 'UNKNOWN_REQUIRES_INSPECTION', **authorization, 'phase': phase,
                'error_type': type(error).__name__, 'timing': timing, 'possible_effect': True,
                'retry_allowed': False, 'reservation_sha256': reservation_hash})
        except Exception:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', required=True)
    parser.add_argument('--expected-proposal-sha256', required=True)
    parser.add_argument('--approval-path', required=True)
    parser.add_argument('--approval-sha256', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = install(args)
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({'status': 'REFUSED_OR_INCOMPLETE',
                          'code': str(error) if isinstance(error, GateError) else type(error).__name__,
                          'reservation_exists': RESERVATION.exists(), 'retry_allowed': False}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
