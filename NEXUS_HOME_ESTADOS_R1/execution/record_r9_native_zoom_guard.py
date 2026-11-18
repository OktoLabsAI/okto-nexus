"""Record native zoom capability without claiming responsive-app acceptance."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/native-zoom-batch/runs/hst-native-zoom-r9-browser-only-2'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    contents = (cut / name).read_bytes()
    assert hashlib.sha256(contents).hexdigest() == digest['sha256'], name
    assert len(contents) == digest['bytes'], name
q = read(cut / 'qualification.json')
result = read(cut / 'native-guard-result.private.json')
assert q['status'] == 'PASS_NATIVE_BROWSER_ONLY'
assert q['before'] == q['after'] and not q['cleanup_errors']
assert not q['forced_births'] and not q['remaining_births'] and q['probe_exit_code'] == 0
assert q['nexus_processes_started'] == q['provider_invocations'] == 0
assert len(result['checks']) == 14 and all(check['pass'] for check in result['checks'])
assert result['observations']['ratios'] == {'dpr': 2, 'innerWidth': .5, 'innerHeight': .5}
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['before']['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Own-profile actual Chrome Settings and static own loopback geometry page; no Nexus or provider started',
    'command_or_procedure': 'Select100% then200% in actual Chrome Page zoom control at unchanged720x1000 viewport; measure actual DPR/CSS viewport/outer/screen/visualViewport and capture executable/birth ancestry',
    'result': 'PASS14 native-browser guard checks: DPR1→2 and CSS720x1000→360x500, unchanged outer/screen, visualViewport.scale1; normal CLI/probe exit, physical absence and source1829/payload1031/tool192 unchanged',
    'limitations': 'Prerequisite only. No responsive Nexus application, long-name interaction, context return, keyboard/AT or whole I05 qualification. Earlier launcher-PID/locale-selector failure retained.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-I05')
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PARTIAL: prior360px app layout plus separate actual native Chrome200% capability proven. Combined app200%/longnames/action access/same-context return remains unexecuted; I05 is not promoted.'
ledger['execution']['r9_native_zoom_prerequisite'] = {
    'status': 'PASS_NATIVE_BROWSER_ONLY', 'qualification': entry['artifact_path'],
    'checks': 14, 'nexus_started': False, 'I05_app': 'NOT_RUN', 'human': 'NOT_INVITED'}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'native_zoom_guard': 'PASS14', 'I05_app': 'NOT_RUN', 'nexus_started': False}))
