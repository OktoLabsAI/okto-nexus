"""Preserve initial qualification and curate only explicitly named final files."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
INITIAL = ROOT / 'public'
PUBLIC = ROOT / 'public-final'


def digest(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


for name, directory, expected in (('initial', INITIAL, 39), ('final', ROOT, 40)):
    run = json.loads((directory / (name + '-result.json')).read_text(encoding='utf-8'))
    assert run['exit_code'] == 0 and run['input_hashes_unchanged']
    assert all(digest(directory / filename)['sha256'] == sha
               for filename, sha in run['input_hashes_before'].items())
    suites = ET.parse(directory / (name + '.xml')).getroot().findall('testsuite')
    counts = {key: sum(int(s.attrib[key]) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    assert counts == {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}

old = (INITIAL / 'token_collector.py').read_text(encoding='utf-8')
new = (ROOT / 'token_collector.py').read_text(encoding='utf-8')
marker = "        if not summary(state)['can_reserve_new_request']:\n"
guard = "        if state['streams'][stream]['retired']:\n            return deepcopy(state), False\n"
assert old.count(marker) == 1 and new == old.replace(marker, guard + marker)
write(ROOT / 'changes.json', {'reason': 'Retired streams reject observation progress and must never admit new work.',
    'semantic_delta': 'reserve returns unchanged state and dispatch False when selected stream is retired',
    'api_changed': False, 'initial_source': digest(INITIAL / 'token_collector.py'),
    'final_source': digest(ROOT / 'token_collector.py'),
    'new_test': 'test_retired_stream_cannot_reserve_after_explicit_epoch_handover',
    'initial_preserved': True, 'final_counts': counts})
write(ROOT / 'final-qualification.json', {'status': 'PURE_PREPARATION_QUALIFIED', 'counts': counts,
    'initial_counts': {'tests': 39, 'failures': 0, 'errors': 0, 'skipped': 0},
    'native_or_provider_campaign': 'NOT_RUN', 'complete_campaign_runner': False,
    'first_setup_usage_observation': 'SEPARATE_CONTROLLER_INTEGRATION_REQUIRED',
    'qualification_runs': ['initial/initial.xml', 'final.xml'],
    'source_unchanged_since_final_tests': True, 'real_native_payloads_retained': False,
    'observed_total_semantics': 'minimum known observed cumulative usage; not final billing or hard cap'})
current = ('token_collector.py', 'test_token_collector.py', 'run_tests.py', 'README.md', 'curate_final.py',
           'final.log', 'final.xml', 'final-result.json', 'final-qualification.json',
           'grounding.json', 'schema-extract.json', 'changes.json')
previous = ('token_collector.py', 'test_token_collector.py', 'run_tests.py',
            'initial.log', 'initial.xml', 'initial-result.json')
PUBLIC.mkdir(exist_ok=False)
(PUBLIC / 'initial').mkdir()
for name in current:
    shutil.copyfile(ROOT / name, PUBLIC / name)
for name in previous:
    shutil.copyfile(INITIAL / name, PUBLIC / 'initial' / name)
allowlist = [*current, *('initial/' + name for name in previous)]
write(PUBLIC / 'artifact-manifest.json', {'format': 1,
    'files': {name: digest(PUBLIC / name) for name in allowlist}})
assert {p.relative_to(PUBLIC).as_posix() for p in PUBLIC.rglob('*') if p.is_file()} == set(allowlist) | {'artifact-manifest.json'}
print(json.dumps({'public': str(PUBLIC), 'payloads': len(allowlist),
                  'manifest': digest(PUBLIC / 'artifact-manifest.json'), 'final_counts': counts}))
