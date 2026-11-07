"""Retain completed installed and browser PR08 artifacts without merging counts."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


INSTALLED_FILES = [
    'build_release.py', 'build_release_v2.py', 'qualify_installed.py',
    'server_entry.py', 'start_server.py', 'smoke_http.py', 'verify_release.py', 'stop_server.py',
    'qualified/package-proof.json', 'qualified/installed-qualification.json',
    'qualified/pr08-observation-installed-initial.xml', 'qualified/real-http-smoke.json',
    'qualified/server-import-proof.json', 'qualified/server.json', 'qualified/server-owner.json',
]
BROWSER_FILES = [
    'pr08-header-menu.yml', 'pr08-observations-dark.png', 'pr08-observations-default.yml',
    'pr08-observations-final.yml', 'pr08-observations-light.png', 'pr08-observations-mobile-dark.png',
    'pr08-observations-saved.yml', 'pr08-settings-check-initial.js', 'pr08-settings-check-save-wait.js',
    'pr08-settings-check-viewport.js', 'pr08-settings-check.js', 'pr08-settings-initial.yml',
    'pr08-settings-menu.yml', 'pr08-settings-reload-diagnostic.yml', 'pr08-settings-result.json',
    'pr08-settings-save-diagnostic.yml', 'pr08-shutdown.json',
]
WHEEL_SHA256 = '85a882cf1ee71ff953e3ce79a25216a1092d0b3a7e314b72527749267e07c130'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def retain(original, target, repo, verify_only):
    before = original.stat()
    data = original.read_bytes()
    after = original.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'Artifact changed during collection: {original}')
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError(f'Refusing to replace different historical evidence: {target}')
    elif verify_only:
        raise FileNotFoundError(target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if target.read_bytes() != data:
        raise ValueError(f'Byte verification failed: {target}')
    return dict(original_path=original.resolve().as_posix(), retained_path=target.relative_to(repo).as_posix(),
                bytes=len(data), sha256=digest(data))


def artifact_set_hash(records):
    pairs = sorted((record['retained_path'], record['sha256']) for record in records)
    return digest(canonical(pairs))


def junit(path):
    root = ET.fromstring(path.read_bytes())
    cases = list(root.iter('testcase'))
    result = dict(tests=len(cases), failures=sum(case.find('failure') is not None for case in cases),
                  errors=sum(case.find('error') is not None for case in cases),
                  skipped=sum(case.find('skipped') is not None for case in cases),
                  duration_seconds=str(sum((Decimal(suite.get('time', '0')) for suite in root.iter('testsuite')), Decimal(0))))
    if result['tests'] != 14 or any(result[key] for key in ('failures', 'errors', 'skipped')):
        raise ValueError('Installed qualification is not the completed fourteen-case green run.')
    return result


def main(repo, installed_root, browser_root, verify_only):
    destination = repo / 'plans/agent_ops/evidence/pr08-observations'
    manifest_path = repo / 'plans/agent_ops/evidence/pr08-observations-tests.json'
    manifest = read_json(manifest_path)
    source_hash = digest(canonical(manifest['source_collection']))
    if manifest['source_collection']['acceptance']['unique_green_cases'] != 525:
        raise ValueError('Unexpected source acceptance; never silently replace its selection.')
    qualified = installed_root / 'qualified'
    package = read_json(qualified / 'package-proof.json')
    qualification = read_json(qualified / 'installed-qualification.json')
    smoke = read_json(qualified / 'real-http-smoke.json')
    imports = read_json(qualified / 'server-import-proof.json')
    owner = read_json(qualified / 'server-owner.json')
    result = read_json(browser_root / 'pr08-settings-result.json')
    shutdown = read_json(browser_root / 'pr08-shutdown.json')
    counts = junit(qualified / 'pr08-observation-installed-initial.xml')

    if not (package['wheel_sha256'] == WHEEL_SHA256 and package['all_raw_bytes_equal']
            and package['exact_relative_sets_equal'] and package['source_unchanged_during_build']
            and package['counts'] == {'python': 486, 'migrations': 164, 'static': 7, 'total': 657}
            and len(package['files']) == 657):
        raise ValueError('Package proof does not match the frozen qualified wheel.')
    if any(not (row['source_sha256'] == row['wheel_sha256'] == row['installed_sha256'])
           for row in package['files'].values()):
        raise ValueError('Package proof contains a raw-byte mismatch.')
    if digest(Path(package['wheel']).read_bytes()) != WHEEL_SHA256:
        raise ValueError('Original wheel bytes do not match their proof.')
    if qualification['exit_code'] != 0 or qualification['xml_sha256'] != digest((qualified / 'pr08-observation-installed-initial.xml').read_bytes()):
        raise ValueError('Installed qualification and JUnit disagree.')
    site = (qualified / 'venv/Lib/site-packages').resolve()
    for modules in (qualification['loaded_package_modules'], imports['modules']):
        if any(not Path(path).resolve().is_relative_to(site) for path in modules.values()):
            raise ValueError('Nexus/Core module originated outside the installed venv.')
    if not (smoke['result'] == 'passed' and len(smoke['checks']) == 49 and smoke['canonical_changed_tables'] == []):
        raise ValueError('Real HTTP smoke is incomplete or changed canonical work.')
    if not (result['status'] == 'PASS' and result['browser'] == '156.0.8078.79'
            and result['controls'] == 16 and result['reloadPreserved']
            and result['invalidTtlDisablesSave'] and result['unrelatedSettingsUnchanged']
            and result['saved'] == {'enabled': True, 'sourceBurst': 21}
            and result['restored'] == {'enabled': False, 'sourceBurst': 20}
            and result['dimensions'] == {'viewport': 390, 'document': 390}
            and result['screenshots'] == 3):
        raise ValueError('Browser result does not satisfy the final settings checks.')
    if not (shutdown['canonical_response']['data']['shutdown']['state'] == 'DRAINED'
            and shutdown['owner_pid'] == owner['server_pid'] == 22456
            and shutdown['launcher_pid'] == owner['launcher_pid'] == 28748
            and shutdown['browser_session_closed'] and shutdown['owner_and_launcher_processes_absent']
            and shutdown['tcp_probe']['connect_result'] == 10035
            and shutdown['tcp_probe']['accepting_connections'] is False):
        raise ValueError('Final lifecycle evidence is incomplete.')
    discovered_browser = sorted(path.name for path in browser_root.glob('pr08*') if path.is_file())
    if discovered_browser != sorted(BROWSER_FILES):
        raise ValueError('Browser file inventory changed; inspect and explicitly update the collection.')

    installed_artifacts = [retain(installed_root / name, destination / 'installed' / name, repo, verify_only)
                           for name in INSTALLED_FILES]
    browser_artifacts = [retain(browser_root / name, destination / 'browser' / name, repo, verify_only)
                         for name in BROWSER_FILES]
    installed_collection = dict(
        original_root=installed_root.resolve().as_posix(), artifacts=installed_artifacts,
        artifact_count=len(installed_artifacts), artifact_set_sha256=artifact_set_hash(installed_artifacts),
        byte_exact_verified=True, wheel_sha256=WHEEL_SHA256, package_payload=package['counts'],
        source_wheel_installed_exact_relative_sets_and_bytes=True,
        junit=counts, junit_report='installed/qualified/pr08-observation-installed-initial.xml',
        http_smoke=dict(status='PASS', checks=49, canonical_changed_tables=[],
                        report='installed/qualified/real-http-smoke.json',
                        scope='Real Uvicorn with ServeLock and synthetic local clients; no real provider participation.'),
        import_proof=dict(nexus_and_core_from_noneditable_venv=True,
                          shared_third_party_dependency_site=imports['shared_dependency_site']),
        diagnostic_note='build_release.py preserves the first diagnostic packaging attempt; build_release_v2.py is the successful follow-up. Launch metadata precedes final browser shutdown.',
        counting_note='Installed pytest cases and HTTP assertions qualify the artifact separately; neither is added to the 525 unique source cases.')
    browser_collection = dict(
        original_root=browser_root.resolve().as_posix(), artifacts=browser_artifacts,
        artifact_count=len(browser_artifacts), artifact_set_sha256=artifact_set_hash(browser_artifacts),
        byte_exact_verified=True, result=result, shutdown=shutdown,
        diagnostic_note='Original failed helper attempts and diagnostic snapshots are preserved. Their recorded locator/wait/viewport failures required helper-only corrections.',
        visual_review='Parent agent inspected the three PNGs; collection verifies hashes and recorded outcomes.',
        shutdown_interpretation='Canonical DRAINED; both known processes absent; probe returned 10035 and did not connect. No claim of connection-refused. Transient Windows Listen PID0 records are recorded in the original JSON.',
        counting_note='Browser controls and actions are not pytest cases and do not change source acceptance counts.')
    all_artifacts = manifest['source_collection']['reports'] + installed_artifacts + browser_artifacts
    additions = dict(installed_collection=installed_collection, browser_collection=browser_collection,
        qualification_summary=dict(source_unique_green_cases=525, installed_pytest=counts,
            real_http_assertions=dict(passed=49), browser_status='PASS',
            retained_original_artifact_count=len(all_artifacts),
            retained_original_artifact_set_sha256=artifact_set_hash(all_artifacts),
            note='These are distinct evidence categories, not an additive test total.'))
    if verify_only:
        for key, value in additions.items():
            if manifest.get(key) != value:
                raise ValueError(f'Manifest mismatch: {key}')
    else:
        manifest.update(additions)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    verified = read_json(manifest_path)
    if digest(canonical(verified['source_collection'])) != source_hash:
        raise ValueError('Source collection changed during integration.')
    return dict(installed_artifacts=len(installed_artifacts), browser_artifacts=len(browser_artifacts),
                retained_original_artifact_count=len(all_artifacts),
                retained_original_artifact_set_sha256=artifact_set_hash(all_artifacts),
                installed_artifact_set_sha256=installed_collection['artifact_set_sha256'],
                browser_artifact_set_sha256=browser_collection['artifact_set_sha256'],
                manifest_sha256=digest(manifest_path.read_bytes()), source_collection_unchanged=True,
                source_unique_green_cases=525, installed_pytest_cases=14, http_checks=49,
                browser_status='PASS', verified_only=verify_only)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--installed-root', type=Path, default=Path('C:/Users/jpamb/AppData/Local/Temp/pr08-installed-wy268uaa'))
    parser.add_argument('--browser-root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    repository = args.repo_root.resolve()
    print(json.dumps(main(repository, args.installed_root, args.browser_root or repository / 'output/playwright', args.verify_only), indent=2))
