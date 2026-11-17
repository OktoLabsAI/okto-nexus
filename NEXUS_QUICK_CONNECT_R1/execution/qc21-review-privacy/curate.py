"""Curate two focal receipts, preserving an abnormal process antecedent."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
roots=[TEMP/'nexus-qc21-review-privacy-2t406fkm',TEMP/'nexus-qc21-review-privacy-_ayk2nlj']
for root,label in zip(roots,['process-antecedent','final']):
    dest=HERE/label
    dest.mkdir(exist_ok=True)
    for path in (root/'review-privacy').iterdir():
        if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
            try:
                value=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                value=path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',value),path.name
            (dest/path.name).write_text(value,encoding='utf-8')
    for name in ('source-pins.json','result.json','pytest.ini'):
        if (root/name).exists():
            shutil.copyfile(root/name,dest/name)
    shutil.copyfile(root/'after/conftest.py',dest/'executed-origin-plugin.py')
    shutil.copyfile(root/'after/tests/quick_connect/test_git_cli_integration.py',dest/'executed-test.py')

final=roots[-1]
cases=list(ET.parse(final/'review-privacy/junit.xml').iter('testcase'))
assert len(cases)==2 and all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
review=json.loads((final/'review-privacy/review-proof.json').read_text())
privacy=json.loads((final/'review-privacy/privacy-proof.json').read_text())
assert review['before_confirmation'] and review['tests']==review['probes']==0 and review['all_effects_printed']
assert privacy['private_origin_absent'] and privacy['resume_json_count']==2
package=TEMP/'nexus-qc-r1-package-t24_dnfc'
payload={}
for module,wheel in [('okto_nexus',package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'),
        ('nexus_connector_core',REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
        ('okto_nexus_connector',REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]:
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                data=(package/'venv/Lib/site-packages'/name).read_bytes()
                assert data==archive.read(name),name
                payload[name]=hashlib.sha256(data).hexdigest()
assert len(payload)==1027
(HERE/'payload-after.json').write_text(json.dumps(payload,indent=2)+'\n')
pins=json.loads((final/'source-pins.json').read_text())
changed=[name for name,pin in pins.items() if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=pin]
assert changed==[],changed
cleanup=subprocess.run([shutil.which('rtk'),'proxy','powershell','-NoProfile','-File',str(HERE/'cleanup-observer.ps1')],
    capture_output=True,text=True,timeout=20,check=True)
cleanup_value=json.loads(cleanup.stdout)
assert cleanup_value['own_candidate_readers']==[]
(HERE/'cleanup.json').write_text(json.dumps(cleanup_value,indent=2)+'\n')
command=[str(package/'venv/Scripts/python.exe'),'-I','-B','-m','pytest','-c',str(final/'pytest.ini'),
    '--rootdir='+str(final/'after'),'--confcutdir='+str(final/'after'),
    str(final/'after/tests/quick_connect/test_git_cli_integration.py'),'-v','-s','-x','-k','monorepo or PRIVATE',
    '--tb=short','-o','faulthandler_timeout=10','--junitxml='+str(final/'review-privacy/junit.xml')]
report=dict(status='FOCAL_ASSERTIONS_PASS_RUNNER_CLEANUP_ASSERTION_PRESERVED',
    passed=2,deselected=8,exact_nodes=[c.get('classname')+'::'+c.get('name') for c in cases],
    argv=command,cwd=str(final/'review-privacy/cwd'),stdin='PIPE closed immediately',deadline_seconds=180,
    installed_python=str(package/'venv/Scripts/python.exe'),
    wheel_sha256=hashlib.sha256((package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest(),
    antecedent_test_sha256='9e6cf1fe0f1c0aaad850ed1f2dbdf6f93dcd031a286bda70d6a30594b90bf78d',
    executed_test_sha256=hashlib.sha256((final/'after/tests/quick_connect/test_git_cli_integration.py').read_bytes()).hexdigest(),
    delta='test-delta.patch',review_proof='final/review-proof.json',privacy_proof='final/privacy-proof.json',
    scenarios=[dict(id='QC-T-F20',proposed_status='PASS',evidence='final/review-proof.json',
        scope='Actual printed canonical review/checkpoint before confirmation; subsequent original Finish/resume invariants retained'),
        dict(id='QC-T-D25',proposed_status='PASS_SCOPED_PERSISTENCE',evidence='final/privacy-proof.json',
        scope='Owned Nexus JSON checkpoints, six compared SQLite tables, both resume JSONs and captured pytest logs; original .git/config excluded input')],
    payload_files=1027,payload_drift=[],repository_input_pins=len(pins),repository_input_drift=changed,
    origins=['final/origins.json','final/origins-finish.json'],
    cleanup='cleanup.json',own_candidate_readers_absent=True,
    process_antecedent=dict(status='INCONCLUSIVE',exit_code=3221225477,
        reason='Windows Python access violation during PRIVATE call, before call report/XML; no assertions qualified',
        evidence='process-antecedent/raw.log',runner_result='process-antecedent/result.json'),
    final_runner=dict(status='POST_PYTEST_CLEANUP_ASSERTION_FAILURE',
        detail='Two pytest call and teardown PASS reports plus terminal XML exist. Wrapper failed its immediate all-retained-handles-dead assertion after launcher exit; no runner.json/result.json was written. Later independent own-root Python/Git process query is empty.',
        signals='No termination was issued; malformed diagnostic observer ended naturally. Subsequent PID stop identity check refused to act.'),
    limitations=[
        'Exactly two tests executed from modified file; eight other tests remain qualified only on the original 9e6cf1fe antecedent.',
        'CLI installed + actual local Git + canonical HTTP/SQLite; input/isatty, lifecycle, version and provider Test peers synthetic, no real PTY/provider/model/authentication.',
        'The privacy assertion is scoped to the listed checkpoints/tables/JSONs/logs. pytest captured zero log messages; this is not universal telemetry audit.',
        'First cut input/payload postchecks passed. Second runner aborted before its postchecks; curation independently compared all source pins and1027 files to exact wheels. Session origins at start and finish were preserved.',
        'No product/normative test/docs/ledger/Git/build/installed package mutation. Raw owned databases, keys and Git input remain Temp only.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC21 review and privacy\n\n**2 focal assertions PASS; 8 deselected.** '
    'F20 checks the real review before confirmation: Git name/source, invocation CWD, effective root, execution host, adapter, proposed ID and all eight effects, with zero Test/probe at that point. '
    'The original monorepo binding/root and synthetic Test/Finish assertions then pass.\n\n'
    'D25 persistence focal verifies that PRIVATE, URL and host are absent from owned Nexus JSON checkpoints, all six compared SQLite table snapshots, and both exact resume JSONs. '
    'Captured pytest logs contain zero messages; no universal telemetry claim. Git config is intentionally excluded as the input.\n\n'
    'The first process had a Windows access violation and remains INCONCLUSIVE. The repetition produced two terminal PASS records/XML, but the runner immediate cleanup-handle assertion failed after pytest. '
    'A later independent process query found no Python/Git reader in the owned root. All1,027 package payload files match the wheels; source pins have zero drift. '
    'The abnormal process and wrapper outcomes remain visible.\n\n'
    'Only these two modified cases were rerun. Eight earlier cases remain tied to their original file hash. No provider, product, normative test, ledger, Git or prefix was changed.\n')
manifest={str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=2,manifest_entries=len(manifest),
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))
