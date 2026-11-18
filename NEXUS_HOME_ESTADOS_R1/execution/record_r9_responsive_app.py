"""Qualify the actual responsive cases without erasing the final-guard failure."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/native-zoom-app-r9-prepared'
base = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for directory in ('focal-i05', 'offline-pin-supplement'):
    for name, digest in read(base / directory / 'manifest.json').items():
        contents = (base / directory / name).read_bytes()
        assert hashlib.sha256(contents).hexdigest() == digest['sha256'], name
        assert len(contents) == digest['bytes'], name
q = read(base / 'focal-i05/qualification.json')
assert q['status'] == 'PASS_FOCAL_I05_BROWSER_WITH_OFFLINE_PIN_SUPPLEMENT'
assert q['original_runtime_exit'] == 1 and q['native_guard_passed'] == 14
assert q['app_bootstrap_passed'] == 4
assert all(case['passed'] == 24 and case['failed'] == 0 for case in q['assertions'].values())
assert q['provider_invocations'] == q['browser_writes'] == q['page_errors'] == 0
assert not any(q['physical'][key] for key in ('remaining_births', 'profile_processes', 'listeners'))
assert q['fixture_cleanup']['exit_code'] == 0 and not q['fixture_cleanup']['signals']
assert q['canonical_close']['unknown'] is True
offline = read(base / 'offline-pin-supplement/qualification.json')
assert offline['matching_original_before'] and offline['probe_worker_and_config_match']
assert offline['checked']['source_commit'] == 'f07163ab7fd618b2ff4247ba6cdb2547b5d4e038'
for phase in ('app-200', 'app-100'):
    raw = read(base / 'runs/hst-native-zoom-r9-app-1' / (phase + '-result.private.json'))
    focuses = [row for row in raw['checks'] if row['id'].startswith('same-context-focus-')]
    assert len(focuses) == 3
    for row in focuses:
        assert row['actual']['tag'] == 'BUTTON'
        assert row['actual']['id'] == row['id'].removeprefix('same-context-focus-')
    scopes = [row for row in raw['checks'] if row['id'].startswith('active-exact-full-scope-')]
    assert len(scopes) == 1 and len(scopes[0]['actual']['scope']) == 12
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': offline['checked']['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/focal-i05/qualification.json',
    'environment': 'Fresh installed R9; actual own-profile Chrome Settings native zoom, canonical Core with inert native peer and original120s question; no provider',
    'command_or_procedure': 'After native14/bootstrap4 prerequisites, operate Active/Needs you/Results at native200%720requested→CSS360 and native100%360requested→CSS360 with long real project labels; strict stack/nooverflow, hit-test/click, exact12-field context/result target, original unanswered request, same-card focus; independent post-exit immutable pin check',
    'result': 'PASS24 application predicates in each case; actual returned focus is BUTTON inside the same canonical card for all six closes; browser writes/errors/provider0, normal CLI/probe/fixture exit and physical absence. Root viewed three representative public PNGs, agent reviewed all six. Later offline check confirms same source1829/payload1031/tool192 and gate/input pins',
    'limitations': 'Original runner exit1 and after=null remain: local card variable a shadowed argparse before final check(a.gate). Pin confirmation is an independent later read-only supplement, not a passing original final guard. B1 close confirmed; A1/A2 canonical closes remain UNKNOWN despite physical absence. Native200 geometry is real, without CSS/deviceScale/PageScale substitution. No full keyboard/AT/theme/real-provider/human qualification.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-I05')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PASS two actual responsive browser cases with native zoom, long names, action hit-tests/exact targets and same-card focus; original runner final-guard failure, independent offline pin proof and two unknown canonical closes retained explicitly.'
ledger['execution']['r9_responsive_application'] = {
    'status': 'PASS_FOCAL_I05_WITH_POST_EXIT_PIN_SUPPLEMENT', 'qualification': entry['artifact_path'],
    'application_checks': 48, 'native_prerequisite_checks': 14, 'bootstrap_checks': 4,
    'original_runner_exit': 1, 'final_original_guard': 'ATTRIBUTEERROR_AFTER_NULL_RETAINED',
    'pin_proof': 'INDEPENDENT_LATER_RO', 'canonical_closes': 'B1_CONFIRMED; A1_A2_UNKNOWN',
    'normal_owner_exit': True, 'physical_absence': True, 'provider_calls': 0}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'I05': 'PASS48_FOCAL', 'original_exit': 1, 'close_A1_A2': 'UNKNOWN_RETAINED'}))
