"""Finish only the separately rerun E16 criterion; preserve predecessor failures."""
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
relative = 'remaining-qualification-r7-next/backend-batch/attempt7-r8-case7/qualification.json'
q = json.loads((HERE / relative).read_text())
assert q['status'] == 'PASS_ONE_FOCAL_CASE' and (q['passed'], q['failed'], q['not_run_selected']) == (1, 0, 0)
assert q['input_readers_released'] and q['physical_same_birth_remaining'] == 0
assert all(not value for value in q['guards'].values())
assert q['actual_semantics']['before']['task_state'] == 'verifying'
assert q['actual_semantics']['after']['task_state'] == 'completed'
assert q['actual_semantics']['after']['verification_evidence_ref']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + relative,
    'environment': 'Actual R8 installed ASGI/SQLite; historical capture/artifact read facts, in-process canonical handoff tool functions and HTTP Seen CAS, copied pinned TypeScript consuming the same API before/after',
    'command_or_procedure': q['node'] + ' (case7 only; six previous PASS cases were not repeated)',
    'result': 'PASS same delivery/three artifacts, finite off-page traversal, current canonical verification/revision, strict presentation enums and badges, Seen changes only selected old result, no ACK of existing deliveries, exact target remains readable; all guards0/physical0',
    'limitations': 'Canonical handoff tool functions are called in-process, not via MCP network transport. Historical capture/receipt/artifact fixture is not three real executions. Source-copy TypeScript is not browser evidence. Cleanup semantics remain unknown before/after; verified delivery does not imply cleanup success. Previous6PASS/1FAIL presentation-oracle result preserved.'}
for test in ledger['tests']:
    if test['id'] == 'HST-T-E16':
        test['status'] = 'PASS'
        existing = next((index for index, old in enumerate(test['evidence'])
            if old.get('artifact_path') == entry['artifact_path']), None)
        if existing is None:
            test['evidence'].append(entry)
        else:
            test['evidence'][existing] = entry
        test['execution_notes'] = entry['result'] + '. ' + entry['limitations']
ledger['execution']['r8_backend_batch']['focal_completion'] = {'evidence': entry['artifact_path'],
    'counts': {'PASS': 1, 'FAIL': 0}, 'selected': 'E16 only', 'prior_six_cases_repeated': False,
    'all_seven_cases_have_pass_evidence_in_separate_cuts': True,
    'original_full_batch_failure_preserved': True, 'real_provider': False}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'E16': 'PASS', 'prior_six_cases_repeated': False}))
