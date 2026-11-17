"""Retain the real R8 focus regression separately from earlier oracle failures."""
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
relative = 'remaining-qualification-r7-next/experience-batch/focus-r8-body-focus-failure/qualification.json'
q = json.loads((HERE / relative).read_text())
assert q['status'] == 'FAIL_FOCUS_RETURN_BODY_AFTER_CANONICAL_MOVE'
checks = {item['id']: item for item in q['results']['close']['checks']}
assert checks['canonical-move-request-and-terminal-delivery']['pass']
assert checks['same-A2-panel-after-column-change']['pass']
assert not checks['focus-return-same-A-or-stable-heading']['pass']
assert checks['focus-return-same-A-or-stable-heading']['actual']['tag'] == 'BODY'
assert not q['physical']['active_resources'] and q['payload_after']['mismatches'] == []
assert q['browser_post_count'] == q['provider_invocations'] == 0
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + relative,
    'environment': 'Actual installed R8 Chrome; fresh canonical A1 working and A2 question with original validity, inert protocol peer',
    'command_or_procedure': 'Observe full exact A tuple move to current/full Needs you plus original A2 request and exact successful A1 delivery; Escape and wait for same-A/stable-heading focus',
    'result': 'FAIL real product focus: exact move and same panel pass; after Escape focus stays BODY through2.5s while A exists only in Needs you',
    'limitations': 'No AT speech/provider claim. Received semantic snapshot has a different revision from host; equality is not required. Automatic CLI cleanup log-name collision required one own-session close under a distinct log; physical absence confirmed. Two of three canonical session closes confirmed, A2 remains unknown.'}
for test in ledger['tests']:
    if test['id'] in ('HST-T-F07', 'HST-T-I02'):
        test['status'] = 'FAIL'
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = 'Real R8 focus regression. Preserve successful exact move/panel predicates; source fix/new installed browser proof required before qualifying the complete scenario.'
ledger['execution']['r8_focus_regression'] = {'evidence': entry['artifact_path'],
    'status': 'FAIL_PRODUCT_BODY_FOCUS', 'correct_scope_and_panel': True,
    'source_fix': 'PENDING_R9', 'human': 'NOT_INVITED', 'provider_invocations': 0}
ledger['execution']['local_usability_candidate']['state'] = 'NOT_READY: reproduced focus-return defect awaiting R9 correction and installed browser verification'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'F07': 'FAIL', 'I02': 'FAIL', 'human': 'NOT_INVITED'}))
