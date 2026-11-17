"""Record literal completed context scenarios from a partially stopped cut."""
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
relative = 'remaining-qualification-r7-next/experience-batch/experience-r8-g01-variant/qualification.json'
q = json.loads((HERE / relative).read_text())
assert q['status'] == 'PARTIAL_G01_G04_POSITIVE_G02_ORACLE_INCOMPLETE'
checks = {item['id']: item for item in q['base']['checks']}
assert all(item['pass'] for item in checks.values())
actual = checks['G01-real-canonical-GET-entire-scope']['actual']
assert actual['expectedScope'] == actual['actualScope'] and len(actual['comparedKeys']) == 12
assert all(q['base_authority_invariants'].values())
assert q['history']['status'] == 'INCOMPLETE'
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
details = {
    'HST-T-G01': ('PASS complete eligible singleton opens in one gesture; actual canonical GET200, all12 scope fields, exact URL target and native output marker match',
        'Canonical inert peer, not a provider. Component direct-selection predicates ran in the404 Node suite; actual browser supplies the separate navigation layer.'),
    'HST-T-G04': ('PASS fresh registered binding with zero sessions opens honest context without creating session/operation, changing grant digest or consuming provider',
        'Observed actual per_sender policy with deferred native opening; no invented on_demand enum. This begins with zero sessions, not a manually closed replacement fixture.'),
}
entries = []
for test in ledger['tests']:
    if test['id'] not in details:
        continue
    result, limits = details[test['id']]
    entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
        'artifact_path': 'execution/' + relative,
        'environment': 'Fresh R8 installed package, own Chrome and canonical Core with inert protocol peer; source-copy/component evidence remains distinct',
        'command_or_procedure': 'G01 direct singleton browser gesture and exact canonical session read; G04 zero-session context, before/after operations and grant digest; Node uiEntryInspection direct-selection contract',
        'result': result, 'limitations': limits + ' Later G02 chooser wait stopped the cut; its original incomplete result is retained and not promoted.'}
    test['status'] = 'PASS'
    if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
        test['evidence'].append(entry)
    test['execution_notes'] = result + '. ' + limits
    entries.append(entry)
for task in ledger['tasks']:
    if task['id'] in ('HST-026', 'HST-028', 'HST-031', 'HST-032'):
        for entry in entries[:1]:
            if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
                task['evidence'].append(entry)
ledger['execution']['r8_context_base'] = {'evidence': 'execution/' + relative,
    'qualified': ['HST-T-G01', 'HST-T-G04'], 'later_cut': 'G02 incomplete selector observation; no cause/product defect established',
    'provider_calls': 0, 'browser_posts': 0, 'human': 'NOT_INVITED'}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'qualified': list(details), 'other_scenarios_promoted': False}))
