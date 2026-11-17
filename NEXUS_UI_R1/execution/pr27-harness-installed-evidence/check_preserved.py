from pathlib import Path
import hashlib, json, zipfile
repo=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
candidate=repo/'NEXUS_UI_R1/execution/pr07-native-proposal/candidate-final.json'
assert sha(candidate)=='3ea51229df9bcc4d93d7f42dbe5e4d62a97741d97c99907a49a21cde6fafb88e'
pins=json.loads(candidate.read_text())['installed_payloads']
mismatch=[item['path'] for item in pins if sha(Path(item['path']))!=item['sha256']]
assert not mismatch,mismatch
checks={'BXP':{'pinned_files':len(pins),'mismatch':mismatch,'candidate_sha256':sha(candidate)}}
for name,folder,relative in [
 ('PR21','nexus-ui-r1-board-pr21-ei6yahi4','artifacts/okto_nexus-0.3.5-py3-none-any.whl'),
 ('PR16','nexus-ui-r1-final-pr16-pxprmqxo','nexus/okto_nexus-0.3.5-py3-none-any.whl'),
 ('PR18','nexus-ui-r1-ux-pr18-shdpm58d','artifacts/okto_nexus-0.3.5-py3-none-any.whl'),
 ('BGONN','nexus-ui-r1-bgon-package-5wwdklas','artifacts/okto_nexus-0.3.5-py3-none-any.whl')]:
    old=root.parent/folder
    wheel=old/relative
    count=0
    with zipfile.ZipFile(wheel) as z:
        for member in z.namelist():
            if member.startswith('okto_nexus/') and not member.endswith('/'):
                assert (old/'venv/Lib/site-packages'/member).read_bytes()==z.read(member),(name,member)
                count+=1
    checks[name]={'wheel_sha256':sha(wheel),'module_payload_files_equal':count}
(root/'preserved-artifacts.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
print(json.dumps(checks,indent=2))
