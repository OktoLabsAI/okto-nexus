"""Qualify the exact R9 focus regression without converting cleanup uncertainty."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / 'package-hst-r9'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


manifest = read(PACKAGE / 'curation-manifest.json')
assert len(manifest) == 42
for name, pin in manifest.items():
    assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == pin, name
ready, package = read(PACKAGE / 'READY.json'), read(PACKAGE / 'qualification.json')
live = read(PACKAGE / 'live-qualification.json')
equivalence = read(PACKAGE / 'runtime-equivalence-vs-r8.json')
presentation = read(PACKAGE / 'presentation-input-equivalence-r8-r9.json')
assert package['status'] == 'PASS_BUILD_INSTALL_SMOKE' and live['status'] == 'PASS'
assert live['cleanup_verified'] and not live['payload_drift'] and live['source_drift'] == []
assert live['provider_calls'] == 0 and not live['process']['remaining_known_processes']
assert not live['process']['remaining_listeners']
assert equivalence['total_runtime_nonstatic_files'] == 1024
assert equivalence['python_version_equal'] and equivalence['dependency_versions_equal']
assert not equivalence['pytest_executed_on_r9'] and not equivalence['browser_evidence_reused']
assert len(presentation['inputs']) == 3
assert all(item['raw_bytes_equal_qualified_copy'] for item in presentation['inputs'])
relative = 'remaining-qualification-r7-next/experience-batch/focus-r9-positive/qualification.json'
q = read(HERE / relative)
assert q['status'] == 'PASS_FOCAL_F07_I02_CANONICAL_MOVE_AND_FOCUS'
assert q['source_commit'] == ready['source_commit'] and q['wheel_sha256'] == ready['wheel_sha256']
assert sum(part['passed'] for part in q['summary'].values()) == 16
assert sum(part['failed'] for part in q['summary'].values()) == 0
assert q['browser_post_count'] == q['provider_invocations'] == 0
assert not q['physical']['active_resources'] and q['payload_after']['mismatches'] == []
assert q['cleanup']['exit_code'] == 0 and not q['cleanup']['signals']
assert q['canonical_close']['unknown'] is True
checks = {item['id']: item for item in q['results']['close']['checks']}
assert checks['focus-return-same-A-or-stable-heading']['actual']['tag'] == 'BUTTON'
assert checks['focus-return-same-A-or-stable-heading']['actual']['harness']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + relative,
    'environment': 'Fresh installed R9 wheel; actual own-profile Chrome and canonical Core with inert protocol peer, original native question validity',
    'command_or_procedure': 'Replay unchanged focus-return.js that failed on R8; observe exact current/full canonical move, original A2 request and exact A1 delivery, close same panel and inspect actual focus/DOM',
    'result': 'PASS16 focal checks: same panel/context survives, A occurs once in Needs you and not Active, Escape restores BUTTON View work inside the same canonical A; no POST/page errors/provider, source/payload1031drift0/normal0/physical0',
    'limitations': 'No AT/native200%/real-provider/performance claim. Host and received revisions may differ; complete semantic identities are asserted. Two of three canonical session closes confirmed; A2 close remains unknown. Physical absence is not all-CLOSED proof. Original real R8 focus failure is retained.'}
for test in ledger['tests']:
    if test['id'] in ('HST-T-F07', 'HST-T-I02'):
        test['status'] = 'PASS'
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = 'Real R8 focus defect resolved and verified on fresh installed R9 using the same predicates; original negative and canonical-close uncertainty retained.'
ledger['execution']['r9_package'] = {'source': ready['source_commit'],
    'wheel_sha256': ready['wheel_sha256'], 'ready': 'execution/package-hst-r9/READY.json',
    'qualification': 'execution/package-hst-r9/qualification.json',
    'live': 'execution/package-hst-r9/live-qualification.json',
    'runtime_equal_files_vs_r8': 1024, 'pytest_r9_executed': False,
    'backend_reuse': 'Exact unchanged backend only: R8 six passing cases plus separate E16 focal; R7 chain retains326/+7 and original limits',
    'typed_presentation_equivalence': 'execution/package-hst-r9/presentation-input-equivalence-r8-r9.json',
    'browser_reuse': False, 'provider_calls': 0, 'default_approved': False}
ledger['execution']['r9_focus_source'].update(status='VERIFIED_FOCAL_F07_I02',
    source_commit=ready['source_commit'], installed='PASS_FRESH_R9_PREFIX',
    browser='PASS16_SAME_MOVE_AND_FOCUS_PREDICATES', browser_evidence=entry['artifact_path'])
ledger['execution']['r8_focus_regression']['status'] = 'RESOLVED_ON_R9; original real failure preserved'
ledger['execution']['r8_focus_regression']['source_fix'] = 'Verified on fresh R9 installed browser; no all-cleanup claim'
ledger['execution']['local_usability_candidate'].update(
    runtime_source=ready['source_commit'], wheel_sha256=ready['wheel_sha256'],
    state='ADDITIONAL_SECURITY_COMPATIBILITY_STREAM_QUALIFICATION_IN_PROGRESS; menu and focus defects resolved',
    pending_local_scopes=['passive/revocation/observation browser security',
        'foreground CLI and active presentation rollback', 'old-producer state read compatibility',
        'stream/validity and remaining literal supported clauses'])
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'F07': 'PASS', 'I02': 'PASS', 'human': 'NOT_INVITED', 'canonical_cleanup': 'A2_UNKNOWN_RETAINED'}))
