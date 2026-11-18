"""Promote literal observed predicates, not entire failed/oracle-limited cuts."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ledger_path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
decision_path = 'browser-hst/nextcuts/r7-decision-offline-derivative/qualification.json'
decision = json.loads((HERE / decision_path).read_text())
assert decision['all_browser_post_count'] == 2 and decision['post_statuses'] == [202, 409]
assert decision['same_decision_get_count'] == 5 and decision['same_decision_get_statuses'] == [200] * 5
assert decision['decision_count'] == decision['native_write_count'] == decision['receipt_count'] == 1
assert decision['no_new_productive_operation'] and decision['recovery_no_additional_post_observed']
assert decision['full_tuple_and_operator_preserved']
paging_path = 'browser-hst/cuts/r7-context-paging-history-partial/context-finish-result.json'
paging = json.loads((HERE / paging_path).read_text())
expected = {'real409-followed-by-current-reread', 'same-panel-and-exact-selection',
            'no-mixed-revision-or-duplicate-options'}
assert {row['id'] for row in paging['checks'] if row['ok']} == expected
assert not paging['posts'] and [row['status'] for row in paging['reads']] == [409, 200]
stamp = datetime.now(UTC).isoformat()


def evidence(artifact, result, procedure, limitations):
    return dict(commit='01b0de385398950ac4547aa8a5dcbc29473c12cb', timestamp=stamp,
        artifact_path='execution/' + artifact, result=result,
        command_or_procedure=procedure,
        environment='Windows; frozen installed R7; own canonical protocol peers/browser profiles; no provider or human',
        limitations=limitations)


recovery = evidence(decision_path,
    'PASS literal D11/D12/H05 predicates: lost202/stale409, repeated same receipt, exactly one durable decision/write admission',
    'Review completed two-context Home/bell browser capture plus independent canonical SQLite snapshots; offline derivative asserts already observed facts',
    'Original browser FAIL remains: an extra oracle inspected losing Home storage. Winner storage and final application-text assertion were not captured. Two UI submissions overlap but second transport waits for first acceptance; no simultaneous DB-transaction or native application/resume claim. GET initiators are not separately attributed.')
paged = evidence(paging_path,
    'PASS literal F05: actual stale409 then current200 in same DOM panel/selection, no mixed or duplicate option IDs',
    'Canonical paginated sessions, new canonical admission, stale next cursor and current reread; current Node controller evidence is separate',
    'The enclosing cut later stopped at an unrelated RuntimeSession field oracle. F14 was reload-only and I06 not run there; those are not promoted by this evidence. Earlier beforeunload cleanup CTRL_BREAK is preserved separately.')
for test in ledger['tests']:
    entry = recovery if test['id'] in ('HST-T-D11', 'HST-T-D12', 'HST-T-H05') else paged if test['id'] == 'HST-T-F05' else None
    if entry is not None:
        test['status'] = 'PASS'
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = entry['limitations']
for task in ledger['tasks']:
    entries = []
    if task['id'] in ('HST-008', 'HST-016', 'HST-025', 'HST-028', 'HST-032'):
        entries.append(recovery)
    if task['id'] in ('HST-019', 'HST-020', 'HST-021', 'HST-024', 'HST-028', 'HST-032'):
        entries.append(paged)
    for entry in entries:
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r7_browser_boundaries'] = dict(
    report='execution/browser-hst/nextcuts-report.md',
    literal_observed_pass=['HST-T-D11', 'HST-T-D12', 'HST-T-H05', 'HST-T-F05'],
    unqualified_by_these_cuts=['winner sessionStorage', 'application/resume text after race',
        'F14 Back/Forward/invalid reference', 'I06 dirty/project/logout'],
    historical_oracle_failures_preserved=True,
    cleanup='All sampled owners/listeners absent; one antecedent CTRL_BREAK/3221225786, others normal0',
    default_rollout=False, real_provider=False, human=False)
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['r7_browser_boundaries']))
