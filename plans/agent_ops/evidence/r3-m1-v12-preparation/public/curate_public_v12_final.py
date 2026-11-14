from pathlib import Path
import json
R=Path(__file__).resolve().parent
notice={'status':'SUPERSEDED_PUBLIC_COUNT_ONLY','path':str(R/'public'),
 'manifest_sha256':'e0d8bea7fae0fa0ceb54f810ed67cec5526dc3d985ef0553b1a7b2eff0c51b68',
 'reason':'Source/driver sanitized XML omit classname; raw(classname,name) failed to deduplicate17 repeated source/affected cases. Tests and proposal unchanged; final uses exact case name with collision review.',
 'reported_unique_before':290,'correct_unique':273,'test_failures_added':0}
(R/'draft/preparation-history/public-counting-attempt.json').write_bytes((json.dumps(notice,indent=2)+'\n').encode())
s=(R/'curate_public_v12.py').read_text().replace("OUT=R/'public'", "OUT=R/'public-final'")
s=s.replace("identities={(c.attrib['classname'],c.attrib['name']) for c in cases}", "identities={c.attrib['name'] for c in cases}")
s=s.replace('Overlapping retained source cases and affected composition cases are deduplicated by classname/name; historical64 and earlier attempts are not added.', 'Source XML omits classname. Exact testcase names deduplicate17 known source/affected overlaps (10discovery+3allocation+4workwrapper); all groups have unique names and no other collisions. Total273=73+76+121+20-17. Historical64 and earlier attempts are not added.')
exec(compile(s,__file__,'exec'))
