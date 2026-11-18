"""Record the actual private-origin/hostile-label overview qualification."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/security-r9-h03-batch/runs/hst-security-r9-h03-private-origin-v2'
cut = HERE / RELATIVE
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_SCOPED' and q['case'] == 'H03'
assert len(q['results']) == 1 and len(q['results'][0]['checks']) == 11
assert all(row['ok'] for row in q['results'][0]['checks'])
assert all(row['method'] == 'GET' for row in q['results'][0]['requests'])
assert q['guards']['equal'] and q['counts']['public_snapshot_tables'] == 30
assert not q['drift'][0]['changes'] and not q['drift'][0]['ignored_tables']
assert not q['drift'][0]['ignored_columns'] and not q['provider_invocations']
assert q['cleanup']['normal'] and q['cleanup']['physical_absence'] and not q['cleanup']['forced']
assert all(row['closed'] for row in q['cleanup']['runtime_close_observations']['sessions'])
assert not q['private_rows_copied'] and not q['raw_auth_copied']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Own-profile actual Chrome; frozen installed R9 HTTP/SQLite; canonical public label and private turn.submit inputs, inert protocol peer',
    'command_or_procedure': 'Admit literal HTML as public workspace label and private prompt plus ESC/Bearer synthetic token via canonical turn.submit; render actual overview JSON/cards, inspect text/DOM/global handler and compare thirty productive tables',
    'result': 'PASS11: exact authorized card and bounded public label, HTML appears as text with no injected element/handler; private marker/token/ESC excluded from overview JSON/DOM, raw JSON control bytes absent; GET-only/pageerrors0/provider0, live30tables identical, pins unchanged and normal exit/physical0 with both canonical session closes confirmed',
    'limitations': 'Literal summary/JSON boundary only. ESC remains at private origin and is not exposed, so this proves minimization rather than deletion/sanitization of ANSI in an authorized terminal. Hostile artifact filenames and authorized transcript are outside this scenario/cut. Synthetic token is not a real credential. Original unexecuted mixed-origin draft retained; browser assertions unchanged. No broad security-family, real harness, human or performance qualification.'}
test = next(row for row in ledger['tests'] if row['id'] == 'HST-T-H03')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = entry['result'] + '. ' + entry['limitations']
ledger['execution']['r9_private_overview'] = {
    'status': 'PASS_H03_OVERVIEW', 'qualification': entry['artifact_path'],
    'browser_checks': 11, 'productive_tables': 30, 'provider_calls': 0,
    'public_origin': 'literal hostile HTML label',
    'private_origin': 'canonical turn.submit prompt plus ESC and synthetic Bearer token',
    'authorized_terminal_ANSI_sanitization': 'NOT_CLAIMED'}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'H03': 'PASS11_OVERVIEW', 'provider_calls': 0}))
