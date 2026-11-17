"""Preserve the failed collection cut; no test body ran and no green relabel."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
dest = HERE/'installed-collection-failure'
dest.mkdir(exist_ok=True)
cuts = []
for shard, suffix in enumerate(('pj35h53y', 'ni6fytip')):
    root = Path('C:/Users/jpamb/AppData/Local/Temp')/('nexus-hst-installed-'+suffix)
    result = json.loads((root/'result.json').read_text(encoding='utf-8'))
    inventory = json.loads((root/'reports/inventory.json').read_text(encoding='utf-8'))
    target = dest/('shard-'+str(shard))
    target.mkdir(exist_ok=True)
    assert result['exit_code'] == inventory['exitstatus'] == 2
    assert not inventory['finished']
    assert not result['source_drift'] and not result['payload_drift'] and not result['helper_drift']
    assert not result['remaining_known_processes'] and not result['timed_out'] and not result['forced']
    for name in ('result.json', 'source-before.json', 'payload-before.json', 'payload-after.json',
            'copied-helpers-before.json', 'copied-helpers-after.json', 'copied-tests.json'):
        shutil.copyfile(root/name, target/name)
    for name in ('stdout.log', 'inventory.json', 'collected.json', 'origins-start.json', 'origins-end.json', 'tests.xml'):
        shutil.copyfile(root/'reports'/name, target/name)
    cuts.append(dict(shard=shard,root=str(root),status='COLLECTION_ERROR',
        collected=len(inventory['collected']),not_run=len(inventory['not_run']),executed=0,
        pytest_exit_code=2,controller_exit_code=1,collection_errors=3 if shard==0 else 2,
        source_pins=1821,payload_files=1031,source_payload_helper_drift=[],remaining_known_processes=[]))
report = dict(status='NOT_GREEN_COLLECTION_ERROR',cuts=cuts,
    executed_tests=0,known_collected_not_run=sum(cut['not_run'] for cut in cuts),
    collection_errors=5,classification='Runner helper namespace setup; parent copied tree is missing from sys.path.',
    proposed_fix='Add only owned copied tree to helper paths, keeping src absent and prefix origin checks intact.',
    workload_caveat='Functional browser ran concurrently; no latency benchmark claim.',
    gate_fail_antecedent='../installed-gate-failure.json',automatic_retry=False)
(dest/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in dest.rglob('*') if p.is_file() and p.name!='manifest.json'}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
