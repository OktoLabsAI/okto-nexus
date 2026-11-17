"""Keep installed RED distinct from externally overlaid proposal qualification."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
roots=[(TEMP/'nexus-qc35-red-oiqzl4wy','installed-red'),
       (TEMP/'nexus-qc35-derived-c_7iftic','derived-green')]
cuts=[]
for root,label in roots:
    out=HERE/label
    out.mkdir(exist_ok=True)
    result=json.loads((root/'result.json').read_text())
    for source,target in [('result.json','result.json'),('source-pins.json','source-pins.json'),
        ('pytest.ini','pytest.ini'),('after/conftest.py','executed-origin-plugin.py'),
        ('after/tests/quick_connect/test_qc35_review_cancel.py','executed-test.py')]:
        shutil.copyfile(root/source,out/target)
    for run in result['cases']:
        dest=out/run['label']
        dest.mkdir(exist_ok=True)
        for path in (root/run['label']).iterdir():
            if path.is_file() and path.suffix in ('.log','.json','.jsonl','.xml'):
                try:
                    text=path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    text=path.read_text(encoding='cp1252')
                assert not re.search(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+',text),path.name
                (dest/path.name).write_text(text,encoding='utf-8')
        assert not run['signals'] and all(not item['alive'] for item in run['processes_after'])
    assert result['payload_files']==1027 and result['payload_drift']==result['repository_input_drift']==[]
    cases=[]
    for run in result['cases']:
        for case in ET.parse(root/run['label']/'junit.xml').iter('testcase'):
            cases.append(dict(node=case.get('classname')+'::'+case.get('name'),
                status='FAIL' if case.find('failure') is not None or case.find('error') is not None else 'PASS',
                evidence=label+'/'+run['label']+'/junit.xml'))
    cuts.append(dict(label=label,root=str(root),cases=cases,
        exit_codes=[run['exit_code'] for run in result['cases']],
        payload_files=1027,payload_drift=[],repository_input_drift=[],signals=[],owned_processes_absent=True))
assert len(cuts[0]['cases'])==1 and cuts[0]['cases'][0]['status']=='FAIL'
assert len(cuts[1]['cases'])==6 and all(case['status']=='PASS' for case in cuts[1]['cases'])
red=json.loads((HERE/'installed-red/cancel/failed-call.json').read_text())
assert "'review' == 'canceled'" in red['failure']
metadata=json.loads((HERE/'overlay-metadata.json').read_text())
assert metadata['not_a_new_wheel'] is True
overlay=Path(metadata['path'])
assert hashlib.sha256(overlay.read_bytes()).hexdigest()==metadata['overlay_sha256']
assert overlay.read_bytes()==(HERE/'derived-connect.py.txt').read_bytes()
for label in ('cancel','choices','json-plan'):
    recorded=json.loads((HERE/'derived-green'/label/'overlay-origin.json').read_text())
    assert recorded['sha256']==metadata['overlay_sha256'] and recorded['derived_not_wheel'] is True
original_choices=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc16-id-choices-final-lpx96e5q/after/tests/quick_connect/test_id_choice_scenarios.py')
copied_choices=roots[1][0]/'after/tests/quick_connect/test_qc35_id_choice_antecedents.py'
assert original_choices.read_bytes()==copied_choices.read_bytes()
shutil.copyfile(copied_choices,HERE/'executed-choice-antecedents.py.txt')
patch_sha=hashlib.sha256((HERE/'connect-cancellation.patch').read_bytes()).hexdigest()
test_sha=hashlib.sha256((HERE/'test_review_cancel.py').read_bytes()).hexdigest()
report=dict(status='INSTALLED_RED_EXTERNAL_DERIVED_PROPOSAL_GREEN_NOT_NEW_WHEEL',
    installed_wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    cuts=cuts,patch='connect-cancellation.patch',patch_sha256=patch_sha,
    test='test_review_cancel.py',test_sha256=test_sha,overlay=metadata,
    installed_current_product=dict(G08='FAIL_REPRODUCED_LAST_DISPLAY_REVIEW',
        C02='All listed subassertions passed before G08 failure; do not promote a coupled failing run to full acceptance'),
    proposal=dict(C02='PASS_DERIVED',G08='PASS_DERIVED',relevant_regressions=5,total_passed=6,
        requires_product_apply_and_new_installed_artifact=True),
    change='Only two added lines in existing new-review answer != y branch: print canceled using existing lifecycle/metadata/effects fields before return0. No input/EOF/approval/checkpoint logic change.',
    safety=dict(repo_product_tests_docs_unchanged=True,installed_prefix_unchanged=True,provider_calls=0,
        own_processes_exited=True,signals=[],only_overlay_module='okto_nexus.adapters.inbound.cli.connect'),
    limits=[
        'This qualifies a reviewable external source overlay, not a new wheel, final installed candidate, release or product ledger promotion.',
        'Baseline RED uses all application modules installed. GREEN explicitly substitutes only connect.py through importlib; all other Nexus/Core/Connector origins remain installed site-packages. Exact overlay path/hash and bounded whitelist are recorded per cut.',
        'Underlying1027 installed payload files and src/tests/docs input pins remain unchanged before/after; overlay bytes are a distinct input, not misreported as installed payload.',
        'C02 proves no usable Git association, basename labeled directory suggestion, create-workspace offer, physical root, zero workspace/ID/grant/binding/receipt/op/session/Test before consent and after cancel, retained review bytes.',
        'Lifecycle is the existing inert ready fixture: ensure was requested once. New canceled document truthfully reports lifecycle_requested=true, canonical_metadata_revalidation_requested=true and effects_started=null; it does not claim zero prior lifecycle effects.',
        'Relevant GREEN regressions are original byte-identical scripted cancel, same/cross-family resume and JSON collision plus installed JSON plan/apply/recovery. No real PTY/human/provider/daemon claim.',
        'No product/normative tests/docs/ledger/Git/installed prefix was edited. Root applies the patch only after frozen readers release and qualifies a newly packaged artifact separately.'
    ])
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(HERE/'report.md').write_text('# QC35 review cancellation proposal\n\n'
    '**Current installed artifact: RED reproduced. External derived proposal:6 PASS.**\n\n'
    'The baseline passes the C02 basename/root/create-offer and zero-authority assertions, but after input n its last display remains review. '
    'The exact failure is preserved.\n\n'
    'The two-line patch prints the existing canceled envelope before returning0: lifecycle requested, canonical metadata revalidation true, effects_started null. '
    'It preserves the unapproved review/checkpoint and changes no stdin/EOF, approval, protocol, flag or Core behavior.\n\n'
    'GREEN uses exactly one explicit external connect.py overlay; it is **not a new wheel**. The new focal passes, alongside five original cancel/resume/JSON regression cases. '
    'All1,027 underlying package files and repository inputs remain unchanged; own processes exited without signals.\n\n'
    'Keep current C02/G08 acceptance partial until Root applies the proposal and qualifies the new installed artifact. '
    'See qualification.json for patch/test/overlay hashes, XML nodes and origin boundaries.\n')
manifest={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(derived_pass=6,installed_red=1,manifest_entries=len(manifest),
    patch_sha256=patch_sha,test_sha256=test_sha,
    qualification_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())))
