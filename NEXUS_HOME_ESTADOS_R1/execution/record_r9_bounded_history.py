"""Qualify bounded history materialization, independently of latency targets."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/j04-bounded-history/attempt3'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_FUNCTIONAL_J04_SCOPE' and q['runner_exit_code'] == 0
assert q['volume']['open_activities'] == 1000 and q['volume']['history_events'] == 100000
assert q['volume']['added_terminal_results'] == q['volume']['artifact_files'] == 25
assert len(q['reads']) == 4 and all(row['http_status'] == 200 for row in q['reads'])
assert all(row['item_count'] == 3 and row['total'] == 25 and row['has_more'] for row in q['reads'][2:])
instrument = q['instrumentation']
assert instrument['guarded_artifact_ids'] == instrument['guarded_canonical_payload_paths'] == 25
assert not instrument['full_payload_materialized'] and instrument['artifact_content_sql_reads'] == 0
assert not instrument['artifact_file_reads']
assert q['guards_before'] == q['guards_after'] and not q['guards_after']['drift']
assert q['original_seed_unchanged'] and not q['latencies_collected'] and q['provider_invocations'] == 0
assert q['physical']['absent_at_curation'] and not q['physical']['remaining']
assert not q['physical']['forced'] and not q['physical']['timeout']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['source_commit'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Installed R9 real ASGI/SQLite, lifespan off; copied owned SQL synthetic1000OPEN/100000event fixture with25 additional terminal captures/artifacts and marked131133-byte fields; no native authority/provider/browser',
    'command_or_procedure': 'Four functional GETs: overview, limited v2 board and two actual results cursor pages; observe unchanged row objects from the installed SQLite factory, forbid artifacts.content SQL reads and opens of all25 resolved canonical payload paths plus the original directory; compare productive rows/pins',
    'result': 'PASS: nonempty metadata, board limit3/preview2, result pages3+3 with disjoint IDs/exact total25 and previews<=401, artifact metadata present. Observed16123 materialized SQL rows/max string17680bytes, zero full-field markers/content SQL reads/protected file opens. Original seed and source1829/payload1031 unchanged, normal worker exit/physical0; no latency collected',
    'limitations': 'SQL synthetic read facts, not valid native receipt/event chains or harness authority. Instrumentation covers GET application materialization and the25 canonical files, not SQLite engine internal I/O, a universal filesystem audit, global memory bound or O(page) cost. Bootstrap initialization/migration is outside the GET window. Attempt1 invalid quick parameter and attempt2 narrower file-hook scope remain preserved. No performance target pass or causal timing regression is inferred.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-J04')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PASS functional J04: actual installed scoped pagination/previews at1000OPEN/100000history and bounded marked-payload materialization/file access. Separate raw timing misses remain diagnostic/non-blocking per user and are not reclassified as numerical passes.'
ledger['execution']['r9_bounded_history'] = {
    'status': 'PASS_J04_FUNCTIONAL_ONLY', 'qualification': entry['artifact_path'],
    'open_activities': 1000, 'history_events': 100000, 'added_results': 25,
    'guarded_canonical_files': 25, 'latencies_collected': False,
    'provider_calls': 0, 'physical_absence': True}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'J04': 'PASS_FUNCTIONAL_ONLY', 'latency_measurements': 0, 'provider_calls': 0}))
