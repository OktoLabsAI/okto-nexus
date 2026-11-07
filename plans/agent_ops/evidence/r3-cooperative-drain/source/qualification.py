"""Collect only closed public reports and the finite Nexus source inventory."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
HERE = Path(__file__).parent
FILES = '''src/okto_nexus/bootstrap/server_shutdown.py
src/okto_nexus/bootstrap/runtime_host.py
src/okto_nexus/bootstrap/server_runtime.py
src/okto_nexus/bootstrap/database_reset.py
src/okto_nexus/bootstrap/embedded_dispatch.py
src/okto_nexus/application/harness_supervisor.py
src/okto_nexus/application/service_lifecycle.py
src/okto_nexus/application/runtime_access.py
src/okto_nexus/application/execution_native_decisions.py
src/okto_nexus/application/execution_dispatch.py
src/okto_nexus/application/execution_capabilities.py
src/okto_nexus/application/execution_leases.py
src/okto_nexus/adapters/inbound/cli/service.py
src/okto_nexus/adapters/inbound/cli/runtime_server.py
src/okto_nexus/adapters/inbound/http/service_lifecycle.py
src/okto_nexus/adapters/inbound/http/app.py
src/okto_nexus/adapters/outbound/service_manager/local.py
src/okto_nexus/adapters/outbound/service_manager/stop_latch.py
tests/execution_r4/test_server_signal_shutdown.py
tests/execution_r4/test_renewal_storage_contention.py
tests/test_service_drain_decision.py
tests/execution_r4/test_service_cooperative_drain.py
tests/execution_r4/test_service_drain_authority.py'''.splitlines()
NODES = '''tests/test_service_drain_decision.py
tests/execution_r4/test_service_cooperative_drain.py
tests/execution_r4/test_service_drain_authority.py
tests/test_service_readiness.py
tests/test_service_start.py
tests/test_user_service_installation.py
tests/execution_r4/test_session_capabilities.py
tests/execution_r4/test_capability_recovery.py
tests/execution_r4/test_native_decisions.py
tests/execution_r4/test_embedded_native_decisions.py
tests/execution_r4/test_shutdown_admission.py
tests/execution_r4/test_server_shutdown.py
tests/execution_r4/test_server_signal_shutdown.py
tests/execution_r4/test_shutdown_storage_order.py
tests/execution_r4/test_reset_connections.py
tests/execution_r4/test_reset_independent_inventory.py
tests/execution_r4/test_renewal_storage_contention.py
tests/execution_r4/test_initial_lease_refusal.py'''.splitlines()
CLASSIFICATION = {
    'initial.xml': 'Five expected failures against the previous implementation: timeout force/retained ownership/safety entry point.',
    'focal-initial.xml': 'Environment collection error: global Python loaded an older Core without user_service_definition. Not product evidence.',
    'focal-correct-environment.xml': 'Strict boolean test expected 400; actual Pydantic validation correctly returned 422. Test expectation corrected.',
    'core-integrated-initial.xml': 'Real integration exposed existing admitted approval denied by the productive send admission fence. Corrected with closed internal continuation actions.',
    'continuation-final.xml': 'Historical filename is misleading: this run overlapped additive Core V2 API changes and is diagnostic only. Four assertions used a steer request missing its required target; corrected.',
    'continuation-v2-initial.xml': 'Inactive actor correctly returned canonical 404 NOT_FOUND, whereas the new test expected 403/409. Expectation corrected specifically.',
    'focused-final.xml': 'Stable 32-case focal run before the additional late-renewal recovery fix; superseded by final regression for overlapping identities.',
    'late-renewal-initial.xml': 'Exact replay of a live renewal already issued was incorrectly denied when its previous lease expired. Initial issue and expired/revoked renewal denials passed.',
    'late-renewal-final.xml': 'Four directed cases passed after exact committed-renewal recovery was preserved.',
    'regression-final.xml': 'Historical filename retained: stable-source regression yielded 245 passed and two old fake-owner fixture failures (missing _lease_wake). Product use of that Event predates this milestone in commit d19d2f103.',
    'renewal-fixture-final.xml': 'Four parameters rerun after adding only the existing owner Event to the synthetic fixture. No product change.',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report(path):
    root = ET.parse(path).getroot()
    suites = list(root.iter('testsuite'))
    return {
        'sha256': sha(path),
        'tests': sum(int(s.attrib['tests']) for s in suites),
        'failures': sum(int(s.attrib['failures']) for s in suites),
        'errors': sum(int(s.attrib['errors']) for s in suites),
        'skipped': sum(int(s.attrib['skipped']) for s in suites),
        'seconds': sum(float(s.attrib['time']) for s in suites),
        'classification': CLASSIFICATION[path.name],
        'identities': sorted({c.get('classname', '') + '::' + c.get('name', '') for c in root.iter('testcase')}),
        'passed_identities': sorted({c.get('classname', '') + '::' + c.get('name', '') for c in root.iter('testcase')
                                     if not any(n.tag in {'failure', 'error', 'skipped'} for n in c)}),
    }


reports = {name: report(HERE / name) for name in CLASSIFICATION}
final = reports['regression-final.xml']
retry = reports['renewal-fixture-final.xml']
assert final['errors'] == final['skipped'] == 0 and final['failures'] == 2
assert retry['errors'] == retry['failures'] == retry['skipped'] == 0
final_passed = set(final['passed_identities']) | set(retry['passed_identities'])
assert set(final['identities']) == final_passed
result = {
    'scope': 'SVC-07 Nexus source implementation and synthetic native-peer regression; no real provider or native user-service campaign.',
    'source_files': {name: sha(ROOT / name) for name in FILES},
    'installed_qualification_nodes': NODES,
    'required_fixture_files': {'plans/contratos/http-target.schema.json': sha(ROOT / 'plans/contratos/http-target.schema.json')},
    'reports': reports,
    'final_unique_identities': len(final_passed),
    'final_passed_identities': sorted(final_passed),
    'fixture_rerun_overlap_with_initial_passes': len(set(final['passed_identities']) & set(retry['passed_identities'])),
    'repeated_focal_identities_are_not_added_to_regression_total': True,
    'lint': {
        'original_22_owned_files': 'python -m ruff check <source_files excluding test_renewal_storage_contention.py> --select E9,F: PASS',
        'legacy_renewal_fixture': 'E9,F reports three unchanged F401/F811 fixture-import diagnostics at line124. E9,F with F401,F811 ignored passes; the only edit is adding _lease_wake=asyncio.Event().',
        'full_rules': 'python -m ruff check execution_leases.py runtime_access.py stop_latch.py and the three new test files: PASS',
        'git_diff_check': 'PASS',
    },
    'limits': [
        'Force does not turn unknown execution into completed work; uncertain native release keeps ownership and storage.',
        'Missing Core drain API or failed/truncated canonical inventory remains pending.',
        'No cancel/reopen transition was added. A separately authorized database reset preserves its existing release-before-erase path.',
        'Source pytest used the isolated valid CI interpreter with current Nexus/Core sources; installed wheel qualification is owned by the parent task.',
        'Ordinary stop omits the new optional force field for compatibility with the older strict endpoint.',
    ],
}
(HERE / 'nexus-source-qualification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'final_unique_identities': result['final_unique_identities'],
                  'report_sha256': sha(HERE / 'nexus-source-qualification.json')}))
