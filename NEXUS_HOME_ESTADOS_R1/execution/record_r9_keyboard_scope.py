"""Record reviewed literal keyboard and wrong-workspace browser qualifications."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / 'remaining-qualification-r7-next'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def frozen(folder):
    for name, value in read(folder / 'manifest.json').items():
        data = (folder / name).read_bytes()
        expected = value['sha256'] if isinstance(value, dict) else value
        assert hashlib.sha256(data).hexdigest() == expected, name
        if isinstance(value, dict):
            assert len(data) == value['bytes'], name


hpath = 'security-r9-h02-batch/runs/hst-security-r9-h02-wrong-workspace'
kpath = 'keyboard-app-r9-prepared/runs/hst-native-zoom-r9-keyboard-3'
h, k = BASE / hpath, BASE / kpath
frozen(h)
frozen(k)
hq, kq = read(h / 'qualification.json'), read(k / 'qualification.json')
assert hq['status'] == 'PASS_SCOPED' and hq['case'] == 'H02'
assert len(hq['results']) == 1 and len(hq['results'][0]['checks']) == 8
assert all(row['ok'] for row in hq['results'][0]['checks'])
assert hq['results'][0]['requests'] == [{'method': 'GET', 'path': '/api/v1/home/target'}]
assert hq['guards']['equal'] and hq['counts']['public_snapshot_tables'] == 30
assert len(hq['drift']) == 1 and not hq['drift'][0]['changes']
assert not hq['drift'][0]['ignored_tables'] and not hq['drift'][0]['ignored_columns']
assert hq['cleanup']['normal'] and hq['cleanup']['physical_absence'] and not hq['cleanup']['forced']
assert all(row['closed'] for row in hq['cleanup']['runtime_close_observations']['sessions'])
assert not hq['provider_invocations'] and not hq['raw_auth_copied'] and not hq['private_rows_copied']
assert kq['status'] == 'PASS_I01_BROWSER_CANONICAL_CLOSE_UNKNOWN'
assert kq['result_summary']['keyboard-case']['passed'] == 190
assert kq['result_summary']['keyboard-case']['failed'] == 0
assert not kq['first_failure'] and not kq['cleanup_errors']
assert kq['before'] == kq['after'] and kq['before']['source_files'] == 1829
assert kq['before']['payload_files'] == 1031 and not kq['provider_invocations']
assert kq['fixture_cleanup']['exit_code'] == 0 and not kq['fixture_cleanup']['signals']
assert not kq['forced_births'] and not any(kq['physical'][key] for key in ('remaining_births', 'profile_processes', 'listeners'))
assert kq['canonical_close']['unknown'] and kq['fixture_cas_redactions'] == 0

path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
timestamp = datetime.now(UTC).isoformat()
entries = {
    'H02': (hpath, hq['source_commit'],
            'Actual own Chrome and frozen installed R9 HTTP/SQLite; two canonical bindings/workspaces, inert protocol peer',
            'Mutate only workspace_id in the real exact-result target GET; retain original target; inspect actual denial, error DOM and captured requests, then compare thirty live productive tables',
            'PASS8: actual409, no protected preview/summary/DOM/counter or runtime control, exactly one GET target and no replacement; thirty whole-table hashes unchanged, no ignored columns; both session closes confirmed, normal exit and physical absence; source1829/payload1031 unchanged',
            'Exact tuple/context denial, not an inter-user/global workspace ACL proof. Other forged dimensions remain separately scoped. No real provider, authority fabrication, performance or human qualification.'),
    'I01': (kpath, kq['before']['source_commit'],
            'Actual own-profile desktop Chrome native100, frozen installed R9 and canonical inert sessions/question/result',
            'Traverse all visible sequential Home controls with real Tab; use keyboard to open exact Active/Needs you/Results contexts, traverse their controls and read-only scroll container, use Escape and verify exact originating card focus',
            'PASS190: Home23/23, Active11/11, Needs22/22, Results19/19 inventories; named controls, painted focus, exact context IDs, Escape returns and PRE ArrowDown/Up40px. Native browser-boundary focus observed without outside-page focus; no POST/page errors/provider calls; normal exits/physical0 and all pins unchanged',
            'No AT speech or human acceptance; I03 remains NOT_RUN. Native dialog may yield to browser chrome: allowed only with hasFocus=false, DOM focus0 and modal still open, followed by bounded return. Static native-focusable PRE is read-only content, not an unnamed action; text/AX hashes and actual scrolling qualify that narrow oracle. Original keyboard-1/2 failures and independent static dialog diagnostic retained; no product change. B1 canonical close confirmed; A1/A2 remain UNKNOWN despite physical absence.')}
for code, (relative, commit, environment, procedure, result, limits) in entries.items():
    test = next(row for row in ledger['tests'] if row['id'] == 'HST-T-' + code)
    artifact = 'execution/remaining-qualification-r7-next/' + relative + '/qualification.json'
    entry = {'commit': commit, 'timestamp': timestamp, 'artifact_path': artifact,
             'environment': environment, 'command_or_procedure': procedure,
             'result': result, 'limitations': limits}
    test['status'] = 'PASS'
    if not any(old.get('artifact_path') == artifact for old in test['evidence']):
        test['evidence'].append(entry)
    test['execution_notes'] = result + '. ' + limits
ledger['execution']['r9_keyboard_and_target_scope'] = {
    'status': 'PASS_I01_H02_SCOPED', 'keyboard_checks': 190, 'wrong_workspace_checks': 8,
    'source_commit': hq['source_commit'], 'provider_calls': 0, 'ui_writes': 0,
    'AT_speech': 'NOT_RUN', 'human': 'NOT_INVITED', 'canonical_keyboard_close': 'A1_A2_UNKNOWN',
    'product_changes': False, 'physical_absence': True}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'I01': 'PASS190', 'H02': 'PASS8', 'AT': 'NOT_RUN', 'human': 'NOT_INVITED'}))
