import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).parent
PREVIOUS = ROOT.parent / 'revision-4/public'
PUBLIC = ROOT / 'public'
PUBLIC.mkdir()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
prior_raw = (PREVIOUS / 'artifact-manifest.json').read_bytes()
assert sha(prior_raw) == '2e16e187edc8fe2a67621e5279ed5d8b9c3eb96adc7d573ce7d6cd130f45b4b2'
prior = json.loads(prior_raw)
qualification = json.loads((ROOT / 'run-001/qualification.json').read_text(encoding='utf-8'))
assert qualification['status'] == 'SYNTHETIC_ONLY_PASS' and qualification['case_count'] == 3
for name, digest in qualification['source_hashes'].items():
    assert sha((ROOT / name).read_bytes()) == digest
assert sha((ROOT / 'owned_job.py').read_bytes()) == prior['files']['owned_job.py']['sha256']
old = (PREVIOUS / 'protected_pty.py').read_text(encoding='utf-8').splitlines(keepends=True)
new = (ROOT / 'protected_pty.py').read_text(encoding='utf-8').splitlines(keepends=True)
(ROOT / 'helper.diff').write_text(''.join(difflib.unified_diff(old, new, fromfile='v4/protected_pty.py', tofile='v5/protected_pty.py')), encoding='utf-8')
historical = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v8-bundle-readonly-5v6lf2u1/review.json')
assert sha(historical.read_bytes()) == 'd82a81a95ad4aa18faee21302e6dd8a877cee4cde9ef418d7082d188e42908b2'
addendum = {
 'status': 'HELPER_ORDERING_FIX_QUALIFIED_WITH_WRAPPER_PRECONDITION',
 'historical_review_sha256': sha(historical.read_bytes()),
 'historical_proposal_sha256': 'eeff7487cfe6dff7e1c865541437d160594e9059482adc795b91b09506e5ec0b',
 'finding': 'HANDOFF_PUBLICATION_AFTER_MATERIAL',
 'resolution': 'V5 holds the key block and waits for the exact complete public handoff marker before one consumer start, while draining the producer. Canonical installed marker is emitted after atomic_json.',
 'caller_preconditions': ['Require the public handoff initially absent before reserving transfer.',
                         'Pass the exact canonical marker with the absolute handoff path.',
                         'Keep canonical Connector handoff scope/content validation and no replay.'],
 'current_cases': 3, 'source_hashes': qualification['source_hashes'],
 'positive_oracles': ['material_seen_before_ready_marker=true', 'consumer_ready_marker_observed=true',
                      'consumer_start_count=1', 'producer_alive_at_consumer_start=true',
                      'producer_exit=consumer_exit=0', 'active_job_processes_after=0'],
 'negative_oracles': 'Missing/deadline and divergent marker both refuse with zero consumers and no delivery attempt; possible producer effects remain true.',
 'limits': ['No real product CLI, service, provider or account ran.',
            'Direct installed terminal/handoff IO functions plus synthetic consumer only; no full handoff schema/authentication qualification.',
            'Root reviews the new wrapper/pins separately. The old eeff snapshot remains blocked and unchanged.']}
(ROOT / 'review-addendum.json').write_text(json.dumps(addendum, indent=2), encoding='utf-8')
files = ['protected_pty.py', 'owned_job.py', 'marker_producer.py', 'marker_consumer.py', 'qualify.py',
         'README.md', 'curate.py', 'helper.diff', 'review-addendum.json', 'run-001/qualification.json']
files += ['run-001/result-' + case['case'] + '.json' for case in qualification['cases']]
entries = {}
def copy(raw, name):
    assert not re.search(rb'nxs_[0-9a-f]{48}', raw), name
    target = PUBLIC / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    entries[name] = {'sha256': sha(raw), 'bytes': len(raw)}
for name in files:
    copy((ROOT / name).read_bytes(), name)
copy(historical.read_bytes(), 'historical-bundle-review.json')
for name in list(prior['files']) + ['artifact-manifest.json']:
    raw = (PREVIOUS / name).read_bytes()
    if name in prior['files']:
        assert sha(raw) == prior['files'][name]['sha256']
    copy(raw, 'history-public-v4/' + name)
manifest = {'schema_version':1, 'revision':5, 'status':'SYNTHETIC_ONLY_QUALIFIED', 'files':entries,
            'current_case_count':3, 'product_cli_calls':0, 'real_credentials':0}
target = PUBLIC / 'artifact-manifest.json'
target.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
assert {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file()} == set(entries) | {'artifact-manifest.json'}
print(json.dumps({'public':str(PUBLIC), 'payloads':len(entries), 'manifest_sha256':sha(target.read_bytes()),
                  'helper_sha256':entries['protected_pty.py']['sha256'],
                  'qualification_sha256':entries['run-001/qualification.json']['sha256'],
                  'addendum_sha256':entries['review-addendum.json']['sha256']}))
