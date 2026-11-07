from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
OUT=ROOT/'plans/agent_ops/evidence/r3-compatibility-boundaries'
assert not OUT.exists()
groups=[('compatibility','r3-rg07-version-pairs-3dwh02v_','db9ec53f1ea14f12d8412bc8a7abdefe64d43ec3f15722079db0cfa295d25633'),
        ('core','r3-rg06-credential-import-1ww0z_4t','c6ac32b34eff0610fd9e5c6c7bc8d5a12027ce08327c36a1b7650151f897c60f')]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
count=0
for name,folder,expected in groups:
    src=TEMP/folder/'public';manifest=src/'manifest.json'
    assert sha(manifest)==expected
    data=json.loads(manifest.read_text(encoding='utf-8'))
    files={x['path']:x['artifact_sha256'] for x in data['artifacts']} if 'artifacts' in data else {k:v['sha256'] for k,v in data.items()}
    assert set(files)|{'manifest.json'}=={p.relative_to(src).as_posix() for p in src.rglob('*') if p.is_file()}
    for path,expected_file in files.items():
        p=src/path
        assert sha(p)==expected_file,path
        assert not re.search(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}',p.read_bytes()),path
    for path in [*files,'manifest.json']:
        dst=OUT/name/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/path,dst);count+=1
shutil.copyfile(__file__,OUT/'prepare.py')
print(json.dumps(dict(public_files_copied=count)))
