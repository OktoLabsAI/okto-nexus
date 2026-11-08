"""Execute only pure preparation checks in the dependencies-only prefix."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent / 'draft'
INSTALL = ROOT / 'installation'
env = json.loads((INSTALL / 'environment.json').read_text())
env['__PYVENV_LAUNCHER__'] = str(INSTALL / 'venv/Scripts/python.exe')
env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
sources = list(ROOT.glob('*.py')) + list((ROOT / 'controller').glob('*.py')) + list(INSTALL.glob('*.py'))
def hashes():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
before = hashes()
with (ROOT / 'pure-tests.stdout.txt').open('xb') as stdout, (ROOT / 'pure-tests.stderr.txt').open('xb') as stderr:
    process = subprocess.Popen(['C:/Python313/python.exe','-I','-B',str(ROOT / 'run_pure_checks.py')],
        cwd=INSTALL / 'isolated', env=env, stdout=stdout, stderr=stderr,
        creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps({'scope':'pure preparation checks only','owned_python_pid':process.pid}),flush=True)
    returncode = process.wait()
after = hashes()
test_counts = None
xml = ROOT / 'pure-tests.xml'
if xml.exists():
    tree = ET.parse(xml)
    nodes = list(tree.iter('testcase'))
    test_counts = {'cases':len(nodes),'failures':len(list(tree.iter('failure'))),
                   'errors':len(list(tree.iter('error'))),'skips':len(list(tree.iter('skipped')))}
report = {'status':'PASS' if returncode == 0 and before == after else 'FAILED_RETAINED',
          'returncode':returncode,'owned_python_pid':process.pid,'tests':test_counts,
          'inputs_unchanged':before == after,'input_hashes_before':before,'input_hashes_after':after,
          'limits':'Pure controller/installer fake-transport tests and entry denial guards; exact Core wheel used only for pure event translation. No native CLI, product installation, provider, service or credential API called.'}
(ROOT / 'pure-tests-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','returncode','tests','inputs_unchanged')}))
raise SystemExit(returncode)
