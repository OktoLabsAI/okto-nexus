"""Curate only completed literal browser predicates; retain stopped/unknown scopes."""
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
relative = 'remaining-qualification-r7-next/experience-batch/experience-r8-session-role/qualification.json'
q = json.loads((HERE / relative).read_text())
assert q['status'] == 'PARTIAL_POSITIVE_UNTIL_MOVED_CLOSE_REVISION_ORACLE'
assert q['physical']['active_resources'] is False and q['payload_after']['mismatches'] == []
assert q['provider_invocations'] == q['browser_post_count'] == 0
assert sum(part['passed'] for part in q['summary'].values()) == 44
assert q['summary']['moved-close']['passed'] == 0
assert q['results']['panel-after']['observations']['f13']['noticeObserved']
assert not q['results']['panel-after']['observations']['f13']['homeAlerts']
assert not q['results']['panel-after']['observations']['f13']['modalAlerts']
cleanup = json.loads((HERE / relative).parent.joinpath('canonical-cleanup-detail.json').read_text())
assert cleanup['unknown'] is True
assert sum(item['close_confirmed'] for item in cleanup['sessions']) == 3
checks = {item['id']: item for item in q['results']['active']['checks']}
labels = checks['G05-authorized-projects-readable']['actual']
assert len(labels) == 6 and all('Harness ID: reviewer' in text for text in labels)
assert all('Project: ' in text for text in labels)
assert 'Project: Alpha project' in labels[0] and 'Project: Beta project' in labels[1]
assert 'Runtime question for the operatorProject: Alpha project' in labels[2]
assert all('Project: Beta project' in text and 'View result' in text for text in labels[3:])

details = {
    'HST-T-F02': 'Other harness B closed canonically; controller received its actual changed revision while the same A question panel/node and exact session stayed open, with normal notice',
    'HST-T-F10': 'Only the external query source raised a real SQLite error; actual board reported unavailable and the exact native session/output remained readable',
    'HST-T-F13': 'A real changed revision produced Home status notices, with no Home or panel role=alert; Node promise/clock tests separately keep normal revisions out of error',
    'HST-T-G02': 'Real canonical preview query returned one session/total2/hasMore; exact card session relation returned200/total2/exact, chooser remained unselected and both exact session outputs were read',
    'HST-T-G05': 'Offline literal review of all six captured DOM rows confirms project labels on both same-public-ID harnesses, the Alpha request and all three Beta deliveries under All projects',
}
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
for test in ledger['tests']:
    if test['id'] not in details:
        continue
    entry = {'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
        'artifact_path': 'execution/' + relative,
        'environment': 'Actual isolated R8 Chrome and installed Nexus/Core with inert protocol fixture; existing component and clock/promise tests remain distinct',
        'command_or_procedure': 'Review actual phase assertions and exact captured DOM/API values against the literal scenario, preserving all earlier oracle failures',
        'result': 'PASS scoped literal criterion: ' + details[test['id']],
        'limitations': 'No provider/AT/full keyboard/native200% zoom claim. G02 preview1 is an explicit real-query variant. Later moved-close hash wait remained incomplete. Canonical cleanup unknown: three of four closes confirmed; normal process exit/physical absence do not resolve the fourth.'}
    test['status'] = 'PASS'
    if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
        test['evidence'].append(entry)
    test['execution_notes'] = details[test['id']] + '. See retained per-layer and cleanup limitations.'
ledger['execution']['r8_experience'] = {'evidence': 'execution/' + relative,
    'qualified': list(details), 'observed_positive_checks': 44, 'whole_cut_green': False,
    'stopped': 'moved-close: exact host revision was not observed; later poll buffer not persisted, cause unproven',
    'partial': ['G03 specific titles', 'G06 full timestamp scenario', 'I01 complete keyboard names/traversal',
        'I04 all states across both themes', 'I05 native200% zoom', 'F07/I02 actual final move/focus'],
    'canonical_cleanup': 'UNKNOWN: three of four session closes confirmed',
    'physical_resources_absent': True, 'provider_invocations': 0, 'human': 'NOT_INVITED'}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'qualified': list(details), 'whole_cut_green': False}))
