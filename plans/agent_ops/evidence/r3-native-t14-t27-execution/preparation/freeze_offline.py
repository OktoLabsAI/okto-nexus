"""Build immutable-review metadata only, never execute the campaign."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def pin(path): return {'path': path.relative_to(root).as_posix(), 'sha256': digest(path), 'bytes': path.stat().st_size}
def save(name, value):
    with (root / name).open('x', encoding='utf-8', newline='\n') as out:
        json.dump(value, out, indent=2); out.write('\n')

assert not (root / 'private').exists() and not (root / 'public').exists()
suite = ET.parse(root / 'tests-offline-final.xml').getroot().find('testsuite')
assert suite.attrib['tests'] == '22' and suite.attrib['failures'] == '0' and suite.attrib['errors'] == '0'
plan = json.loads((root / 'plan.json').read_bytes())
save('qualification-offline.json', {'status': 'OFFLINE_QUALIFIED_NOT_EXECUTED', 'tests': 22, 'passed': 22,
    'initial': {'passed': 21, 'failed': 1, 'cause': 'Test compared installed parser Path with string; corrected assertion to Path.',
                'xml': pin(root / 'tests-offline-initial.xml')},
    'final': pin(root / 'tests-offline-final.xml'), 'runner': pin(root / 'run.py'), 'tests_source': pin(root / 'test_runner.py'),
    'package_proof': pin(root / 'package-proof-offline.json'), 'native_service_operations_executed': 0,
    'provider_calls': 0, 'login_attempts': 0, 'real_scenario_acceptance': False})
runtime = [root / 'run.py', root / 'plan.json']
save('freeze.json', {'status': 'AWAITING_ROOT_REVIEW_AND_EXECUTION', 'runtime': [pin(p) for p in runtime],
    'execute_argv': [plan['python'], '-I', '-B', '-X', 'utf8', str(root / 'run.py'), 'execute',
                     '--expected-plan-sha256', digest(root / 'plan.json'), '--expected-runner-sha256', digest(root / 'run.py')],
    'qualification': pin(root / 'qualification-offline.json'),
    'prohibited': ['provider inference', 'login', 'force', 'automatic resubmit', 'M1 service or data mutations'],
    'limits': plan['limits']})
paths = [root / n for n in ['run.py', 'prepare.py', 'plan.json', 'test_runner.py', 'README.md', 'freeze_offline.py',
    'package-proof-offline.json', 'tests-offline-initial.xml', 'tests-offline-final.xml', 'qualification-offline.json', 'freeze.json']]
save('public-allowlist.json', {'files': [pin(p) for p in paths]})
print(json.dumps({'freeze_sha256': digest(root / 'freeze.json'), 'allowlist_sha256': digest(root / 'public-allowlist.json'),
                  'plan_sha256': digest(root / 'plan.json'), 'runner_sha256': digest(root / 'run.py')}))
