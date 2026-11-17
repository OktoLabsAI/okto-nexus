"""Curated v2 delta; keep previous proposal and its six results unchanged."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
PARENT=HERE.parent
root=Path(json.loads((HERE/'allocation.json').read_text())['root'])
package=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc')
out=HERE/'final'
out.mkdir(exist_ok=True)
for source,target in [('source-pins.json','source-pins.json'),('pytest.ini','pytest.ini'),
    ('after/conftest.py','executed-origin-plugin.py'),
    ('after/tests/quick_connect/test_qc35_review_cancel.py','executed-test.py')]:
    shutil.copyfile(root/source,out/target)
cases=[]
own=[]
excluded=[]
raw_hashes={}
for label in ('variants','json-plan'):
    dest=out/label
    dest.mkdir(exist_ok=True)
    for path in (root/label).iterdir():
        if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
            raw_hashes[label+'/'+path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name=='runner.json':
                run=json.loads(path.read_text())
                by_pid={p['pid']:p for p in run['processes_after']}
                for child in run['processes_after']:
                    parent=by_pid.get(child['parent_pid'])
                    if parent and child['birth_filetime']<parent['birth_filetime']:
                        excluded.append(dict(pid=child['pid'],claimed_parent_pid=parent['pid'],
                            birth_filetime=child['birth_filetime'],parent_birth_filetime=parent['birth_filetime'],
                            reason='Child predates claimed parent; stale/reused parent PID, not owned',signal_sent=False))
                        # Keep only the minimum PID/time proof about this nonowned
                        # process, even if a future observer records extra fields.
                        child.clear()
                        child.update(excluded[-1])
                    else:
                        assert child['alive'] is False
                        own.append(dict(pid=child['pid'],birth_filetime=child['birth_filetime'],exited=True))
                assert run['exit_code']==0 and run['signals']==[]
                (dest/path.name).write_text(json.dumps(run,indent=2)+'\n')
                continue
            try:
                text=path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                text=path.read_text(encoding='cp1252')
            assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',text),path.name
            (dest/path.name).write_text(text,encoding='utf-8')
    for case in ET.parse(root/label/'junit.xml').iter('testcase'):
        assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
        cases.append(dict(node=case.get('classname')+'::'+case.get('name'),evidence='final/'+label+'/junit.xml',status='PASS'))
assert len(cases)==3 and len(excluded)==1
assert excluded[0]['birth_filetime']<excluded[0]['parent_birth_filetime']
(HERE/'nonowned-pid-minimum-proof.json').write_text(json.dumps(excluded,indent=2)+'\n')
(HERE/'raw-input-hashes.json').write_text(json.dumps(raw_hashes,indent=2)+'\n')
assert (PARENT/'qualification.json').exists()
antecedent_sha=hashlib.sha256((PARENT/'qualification.json').read_bytes()).hexdigest()
assert antecedent_sha=='211852d056b1cf1cde355d227216d78507813ce0d6e4ede08c1d2b7a328e4389'
quick=json.loads((out/'variants/g08-proof-quick.json').read_text())
legacy=json.loads((out/'variants/g08-proof-legacy.json').read_text())
assert quick['canonical_metadata_revalidation_requested'] is True
assert legacy['canonical_metadata_revalidation_requested'] is False
assert all(proof['state']=='canceled' and proof['lifecycle_requested'] is True and proof['effects_started'] is None
           and proof['checkpoint_preserved'] for proof in (quick,legacy))
overlay=root/'overlay/connect.py'
overlay_sha=hashlib.sha256(overlay.read_bytes()).hexdigest()
assert overlay.read_bytes()==(HERE/'derived-connect-v2.py.txt').read_bytes()
assert b'canonical_metadata_revalidation_requested=canonical_metadata, effects_started=None' in overlay.read_bytes()
payload={}
for module,wheel in [('okto_nexus',package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'),
    ('nexus_connector_core',REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
    ('okto_nexus_connector',REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]:
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                content=(package/'venv/Lib/site-packages'/name).read_bytes()
                assert content==archive.read(name),name
                payload[name]=hashlib.sha256(content).hexdigest()
assert len(payload)==1027
(HERE/'payload-after.json').write_text(json.dumps(payload,indent=2)+'\n')
pins=json.loads((root/'source-pins.json').read_text())
drift=[name for name,pin in pins.items() if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=pin]
assert drift==[],drift
script="Get-CimInstance Win32_Process -Filter \"(Name='python.exe' OR Name='git.exe') AND CommandLine LIKE '%nexus-qc35v2-derived-rk0m36g2%'\" | Select-Object ProcessId,ParentProcessId,CreationDate | ConvertTo-Json -Depth 3"
(HERE/'own-reader-check.ps1').write_text(script+'\n')
observed=subprocess.run([shutil.which('rtk'),'proxy','powershell','-NoProfile','-File',str(HERE/'own-reader-check.ps1')],
    capture_output=True,text=True,timeout=20,check=True)
assert not observed.stdout.strip(),observed.stdout
cleanup=dict(actual_owned_process_handles=own,owned_namespace_readers=[],nonowned_process_proof='nonowned-pid-minimum-proof.json',
    no_signal_or_stop_issued=True)
(HERE/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
patch_sha=hashlib.sha256((HERE/'connect-cancellation-v2.patch').read_bytes()).hexdigest()
test_sha=hashlib.sha256((HERE/'test_review_cancel_v2.py').read_bytes()).hexdigest()
report=dict(status='THREE_DERIVED_FOCALS_PASS_OBSERVER_FALSE_CHILD_PRESERVED',passed=3,cases=cases,
    previous_six_passed_report='../qualification.json',previous_report_sha256=antecedent_sha,
    previous_patch_unchanged_sha256=hashlib.sha256((PARENT/'connect-cancellation.patch').read_bytes()).hexdigest(),
    patch='connect-cancellation-v2.patch',patch_sha256=patch_sha,test='test_review_cancel_v2.py',test_sha256=test_sha,
    overlay_sha256=overlay_sha,overlay_module='okto_nexus.adapters.inbound.cli.connect',not_a_new_wheel=True,
    quick=quick,legacy=legacy,cleanup='cleanup.json',payload_files=1027,payload_drift=[],repository_input_drift=[],
    observer_outcome=dict(status='WRAPPER_ASSERTION_FAILED_FALSE_DESCENDANT',
        detail='Both pytest phases exit0; immediate cleanup classified an older unrelated process as child through stale parent PID. Birth ordering disproves ownership. No signal was sent. Original raw remains Temp with hashes; curated nonowned data contains only necessary PID/times.',
        raw_hashes='raw-input-hashes.json',minimum_proof='nonowned-pid-minimum-proof.json',
        future_runner_requirement='Require child creation time >= actual retained parent creation time before ownership attribution or any containment.'),
    limits=[
        'Exactly two new parameter variants plus one relevant existing JSON plan/recovery focal executed; previous six results and previous patch remain unchanged.',
        'The revised two-line proposal uses the existing canonical_metadata variable, preserving true in Quick and false in explicit-profile legacy without catalog selection.',
        'Quick alone qualifies basename/directory suggestion, root and create offer with zero authority/Test before consent; legacy only proves its explicit client/project/profile selection and no Git discovery.',
        'All other application modules are installed site-packages; connect.py alone is an explicit external overlay. Package files unchanged does not mean the overlay is a released wheel.',
        'Wrapper postchecks were interrupted by the false-descendant assertion; curation independently rechecked1027 exact wheel payload files and every source pin. Start/finish origins and overlay hashes are preserved per phase.',
        'Actual owned processes exited; an unrelated reused-PID record is not claimed killed/owned. No unrelated image path or command line is curated.',
        'No repo src/tests/docs, prefix, Git, ledger, provider, personal credentials or Windows service was changed. Product acceptance still needs Root apply and final artifact qualification.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC35 revision2: truthful legacy metadata\n\n'
    '**3 derived focals PASS:** Quick cancellation, explicit-selector legacy cancellation and the existing JSON plan/recovery node. '
    'Both cancel documents retain the review, lifecycle_requested true and effects_started null; metadata revalidation is true only for Quick and false for the legacy profile path.\n\n'
    'The prior patch and six PASS results remain immutable antecedents. This revision changes only the metadata expression to the existing canonical_metadata variable. '
    'One explicit connect.py overlay is qualified; no new wheel or product-source change is claimed.\n\n'
    'The runner cleanup assertion had a false child because the recorded child predates its alleged parent. No signal was sent; unrelated paths/command lines are omitted. '
    'Actual owned handles show exit and the owned-root process query is empty. Independent curation checks confirm1027 unchanged package files and zero source drift. '
    'See qualification.json for precise hashes, XML nodes and the preserved observer limitation.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(passed=3,manifest_entries=len(manifest),patch_sha256=patch_sha,test_sha256=test_sha,
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))
