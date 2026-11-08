"""Preserve the initial curation; add only five explicitly approved diagnosis files."""
from pathlib import Path
import hashlib,json,re,shutil
R=Path(__file__).resolve().parent;OLD=R/'public';OUT=R/'public-final'
DIAG=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-sqlite-reader-diagnosis-qa6r8kmw')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
assert sha(DIAG/'diagnosis.json')=='6b76e393bef4b16f78760997cf3f74be126bbf5417f04cbffac60aa803f38d3a'
d=read(DIAG/'diagnosis.json');prior=read(OLD/'artifact-manifest.json')
assert set(d['evidence_files'])=={'probe.py','probe.json','native_probe.py','native-probe.json'}
assert d['db_sha256_before']==d['db_sha256_after']
assert not OUT.exists();OUT.mkdir()
entries=[]
for entry in prior['artifacts']:
    source=OLD/entry['path'];assert sha(source)==entry['artifact_sha256']
    target=OUT/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    entries.append(dict(entry))
pin={**d['evidence_files'],'diagnosis.json':sha(DIAG/'diagnosis.json')}
for name,digest in pin.items():
    source=DIAG/name;assert sha(source)==digest
    raw=source.read_bytes();assert not re.search(rb'nxs_[0-9a-fA-F]{48}',raw)
    target=OUT/'offline-diagnosis'/name;target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
    entries.append({'path':target.relative_to(OUT).as_posix(),'source_path':str(source),'source_sha256':digest,
        'artifact_sha256':sha(target),'bytes':len(raw),'transformation':'byte_exact','redactions':0})
summary=read(OUT/'summary.json')
summary['separate_offline_diagnosis']={'path':'offline-diagnosis/diagnosis.json','sha256':pin['diagnosis.json'],
    'db_unchanged_in_report':d['db_sha256_before']==d['db_sha256_after'],
    'finding':'New-connection schema compilation reached the40ms whole-open observer deadline in the separate reproduction; the C API returned SQLITE_INTERRUPT during sqlite3_prepare_v2 before sqlite3_step.',
    'interpretation':'A sufficient matching mechanism, not a retrospective measurement of the exact original scheduling interval. Cold means connection/schema-cache cold; OS file cache was not purged.',
    'instrumentation_history':'An initial C probe omitted sqlite3_initialize and failed before opening the DB. This probe defect is retained in diagnosis.json; it is not a product failure.',
    'executed_by_this_collector':False,'candidate_code_included':False}
summary['limits'][1]='The observer failure is distinct from prior v9 product DB_ERROR. The separately retained offline reproduction establishes a matching initialization/deadline mechanism; original phase timings and numeric SQLite code were not retained. This collector performs no reproduction or database access.'
target=OUT/'summary.json';target.write_bytes((json.dumps(summary,indent=2,ensure_ascii=False)+'\n').encode())
entry=next(v for v in entries if v['path']=='summary.json')
entry.update(artifact_sha256=sha(target),bytes=target.stat().st_size,source_path='generated reconciliation with separate root-approved offline diagnosis',source_sha256=None)
for source,name in [(Path(__file__),'append_diagnosis.py'),(OLD/'artifact-manifest.json','history/pre-diagnosis-manifest.json')]:
    target=OUT/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
    entries.append({'path':name,'source_path':str(source),'source_sha256':sha(source),'artifact_sha256':sha(target),
        'bytes':target.stat().st_size,'transformation':'byte_exact','redactions':0})
assert all(sha(DIAG/name)==digest for name,digest in pin.items())
assert sha(OLD/'artifact-manifest.json')=='e01788c2e8d24c0521b3ac1f9ee0413021a705f25006a09d4724591964a95d46'
entries.sort(key=lambda e:e['path'])
aggregate=hashlib.sha256(''.join(e['path']+'\0'+e['artifact_sha256']+'\n' for e in entries).encode()).hexdigest()
m={'format':'okto.public-artifact-allowlist','revision':2,'artifact_count':len(entries),'aggregate_sha256':aggregate,
    'artifacts':entries,'redactions':0,'all_sources_unchanged':True,
    'copy_policy':'Exact metadata/script allowlist; original49-artifact public curation remains unchanged. Added only diagnosis.json plus its four pinned evidence files, with explicit summary attribution.',
    'private_exclusions':['raw logs','raw checkpoint','databases','vaults','provider state','candidate observer code']}
target=OUT/'artifact-manifest.json';target.write_bytes((json.dumps(m,indent=2,ensure_ascii=False)+'\n').encode())
print(json.dumps({'public':str(OUT),'manifest_sha256':sha(target),'aggregate_sha256':aggregate,'artifact_count':len(entries),
    'summary_sha256':sha(OUT/'summary.json'),'closure_sha256':sha(OUT/'campaign/closure.json'),
    'checkpoint_projection_sha256':sha(OUT/'controller-checkpoint-projection.json'),'redactions':0}))
