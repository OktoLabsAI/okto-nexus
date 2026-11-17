"""Resolve the reproduced naming defect without qualifying all keyboard flows."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUT = HERE / 'remaining-qualification-r7-next/experience-batch/naming-r8'
qpath = CUT / 'qualification.json'
assert hashlib.sha256(qpath.read_bytes()).hexdigest() == 'a4881d77f133941db204d9a0e130aef16482dad5b642d48e7c9dd012418d94b8'
q = json.loads(qpath.read_text())
assert q['status'] == 'PASS_FOCAL_ACCESSIBLE_NAME_EXPANDED'
assert len(q['runtime']['checks']) == 5 and all(item['pass'] for item in q['runtime']['checks'])
assert q['cleanup']['exit_code'] == 0 and not q['cleanup']['signals']
assert not q['physical']['active_resources'] and q['payload_after']['mismatches'] == []
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
entry = dict(commit=q['source_commit'], timestamp=datetime.now(UTC).isoformat(),
    artifact_path='execution/' + qpath.relative_to(HERE).as_posix(),
    environment='Fresh installed R8 wheel; actual own Chrome accessible tree, two registered connections, zero native sessions',
    command_or_procedure='Read actual header menu AX name; toggle open/closed and compare aria-expanded; audit browser POST/errors and owned cleanup',
    result='PASS five focal assertions: Application menu, expanded false/true/false, no POST/page errors; normal0/physical0/payload1031drift0',
    limitations='Resolves the real R7 defect; original negative evidence retained. Complete keyboard journey and AT speech are not qualified by this focal cut.')
for test in ledger['tests']:
    if test['id'] == 'HST-T-I01':
        test['status'] = 'NOT_RUN'
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = 'Real R7 unnamed menu defect resolved and verified on installed R8 in actual Chrome AX; complete literal keyboard journey remains pending, so no whole-scenario PASS.'
for task in ledger['tasks']:
    if task['id'] in ('HST-026', 'HST-028', 'HST-031', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r8_menu_accessibility'].update(browser='PASS_FOCAL_NAME_AND_EXPANDED',
    browser_evidence=entry['artifact_path'], original_r7_defect='RESOLVED_ON_R8; negative capture preserved',
    complete_keyboard='NOT_YET_QUALIFIED')
ledger['execution']['local_usability_candidate']['state'] = 'ADDITIONAL_FUNCTIONAL_QUALIFICATION_IN_PROGRESS; R8 menu correction verified in actual browser'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'RECORDED', 'I01': 'NOT_RUN_COMPLETE_SCENARIO', 'focal_regression': 'RESOLVED'}))
