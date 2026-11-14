from pathlib import Path
import difflib,hashlib,json
R=Path(__file__).resolve().parent;D=R/'draft';OLD=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/public-operator-final/draft')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
records=[];diff=D/'diffs';diff.mkdir(exist_ok=True)
for f in [*D.glob('*.py'),*(D/'controller').glob('*.py'),*(D/'installation').glob('*.py')]:
 relative=f.relative_to(D);previous=OLD/str(relative).replace('m1_v12','m1_v11')
 if not previous.exists():continue
 same=sha(f)==sha(previous)
 record={'path':relative.as_posix(),'source_path':str(previous),'source_sha256':sha(previous),'sha256':sha(f),'byte_identical':same}
 if not same:
  target=diff/(relative.as_posix().replace('/','__')+'.diff')
  target.write_bytes(''.join(difflib.unified_diff(previous.read_text().splitlines(True),f.read_text().splitlines(True),fromfile='v11/'+previous.name,tofile='v12/'+f.name)).encode())
  record['diff']=str(target)
 records.append(record)
v={'status':'REVIEWABLE_V12_REBASE','schema_format':11,'campaign_policy_revision':12,
 'schema_note':'Persisted controller schema remains11; no structural change. Policy/receipt revision12 and new root reject old campaign state and receipt.',
 'deltas':['carry7 +new5 =cumulative12; token limits and ancestor faults preserved','new labels, own paths/task identities/port58631','setup_journal discovery fix from qualified3efa6edf freeze','strict local-only final-presence and raw Connector representation pending separate driver freeze'],
 'records':records,'provider_or_service_actions':0}
(D/'v12-rebase-review.json').write_bytes((json.dumps(v,indent=2)+'\n').encode())
print(json.dumps({'files':len(records),'changed':sum(not v['byte_identical'] for v in records)}))
