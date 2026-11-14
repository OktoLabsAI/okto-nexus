from pathlib import Path
import json,re,shutil
R=Path(__file__).resolve().parent;D=R/'draft';I=D/'installation'
p=json.loads((D/'m1-codex-campaign-proposal-v12.json').read_bytes())
f=I/'timed_install.py';s=f.read_text()
s=re.sub(r'^ROOT = .*$', lambda _: 'ROOT = Path('+repr(I.as_posix())+')',s,flags=re.M)
s=re.sub(r'^CAMPAIGN = .*$', lambda _: 'CAMPAIGN = Path('+repr((R/'campaign').as_posix())+')',s,flags=re.M)
s=s.replace('M1 v11','M1 v12').replace('current v11','current v12');f.write_bytes(s.encode())
f=I/'test_timed_install.py';s=f.read_text().replace("'revision': 11","'revision': 12").replace('test_exact_v11','test_exact_v12');f.write_bytes(s.encode())
f=D/'controller/test_v11_allocation.py';s=f.read_text().replace("'revision':11,'carry_in_admissions':6","'revision':12,'carry_in_admissions':7")
s=s.replace("'max_cumulative_admissions':11","'max_cumulative_admissions':12")
s=s.replace('c3d3e5f5b5b8fbec2c86ea711350ba1a7de44022e568b1c6cfc4fe2e93ff6db0',p['controller_preparation']['ancestry']['closure_sha256'])
s=s.replace("==6+index+1","==7+index+1").replace("['reserved_requests']==11","['reserved_requests']==12")
f.write_bytes(s.encode())
old=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z')
for name in ('test_lifecycle_cleanup_pending.py','qualify_lifecycle_cleanup.py','requirements_lf.py'):
 (R/name).write_bytes((old/name).read_text().replace('m1_v11','m1_v12').encode())
print('Affected checks prepared; no campaign effects')
