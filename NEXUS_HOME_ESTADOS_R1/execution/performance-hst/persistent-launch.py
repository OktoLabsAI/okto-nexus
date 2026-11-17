"""PREPARED counterpart launcher; explicit future exclusive window required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def schema(db):
    with sqlite3.connect(db) as c:
        rows=list(c.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--window',choices=['PERF_WINDOW_OPEN'],required=True)
    p.add_argument('--ready',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--connections',type=int,choices=[1,10,100],required=True)
    p.add_argument('--variant',choices=['baseline-v1','candidate-v1','candidate-v2'],required=True)
    p.add_argument('--label',required=True)
    a=p.parse_args()
    assert a.label and all(x.isalnum()or x in '-_' for x in a.label)
    evidence=HERE/('persistent-'+a.label+'-launch.json')
    assert not evidence.exists(),'Never overwrite/replay an antecedent'
    ready=json.loads(a.ready.read_text(encoding='utf-8'))
    assert ready.get('ready') and ready.get('prefix_frozen') and sha(Path(ready['wheel']))==ready['wheel_sha256']
    source=a.dataset.resolve();manifest=json.loads(source.read_text(encoding='utf-8'))
    owner=source.parent
    assert json.loads((owner/'.hst-owned.json').read_text())==dict(root=str(owner),kind='hst-performance-synthetic-only')
    assert owner.name.startswith('nexus-hst-performance-')
    case=next(c for c in manifest['cases'] if c['size']==a.connections)
    seed_name='seed-'+str(a.connections)+('-open' if manifest.get('workload')=='J04-open-complement' else '')
    seed=(owner/seed_name/'home').resolve()
    assert seed.is_relative_to(owner)
    assert sha(seed/case['db_relative'])==case['database_sha256']
    assert schema(seed/case['db_relative'])==case['schema_sha256']
    root=Path(tempfile.mkdtemp(prefix='nexus-hst-performance-persistent-driver-')).resolve()
    dataset=root/'nexus-hst-performance-persistent-dataset';dataset.mkdir()
    (dataset/'.hst-owned.json').write_text(json.dumps(dict(root=str(dataset),kind='hst-performance-synthetic-only')))
    target=dataset/('case-'+str(a.connections))/a.variant
    target.parent.mkdir()
    shutil.copytree(seed,target) # Never modify/reset/reuse a measured clone.
    assert sha(target/case['db_relative'])==case['database_sha256']
    derived_case={**case,'clones':{a.variant:str(target)}}
    derived={**manifest,'cases':[derived_case],'persistent_antecedent':dict(dataset=str(source),sha256=sha(source),seed_db_sha256=sha(seed/case['db_relative']))}
    derivative=dataset/'dataset.json';derivative.write_text(json.dumps(derived,indent=2)+'\n')
    cwd=root/'cwd';cwd.mkdir();output=dataset/'reports/result.json'
    env={k:v for k,v in os.environ.items() if k.upper()in {'SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','PATHEXT'}}
    env['PATH']=str(Path(ready['python']).parent)
    for key,name in [('HOME','profile'),('USERPROFILE','profile'),('APPDATA','roaming'),('LOCALAPPDATA','local')]:
        d=root/name;d.mkdir(exist_ok=True);env[key]=str(d)
    env.update(TMP=str(root),TEMP=str(root),CODEX_HOME=str(root/'missing-codex'),CLAUDE_CONFIG_DIR=str(root/'missing-claude'),PI_CODING_AGENT_DIR=str(root/'missing-pi'))
    command=[ready['python'],'-I','-B','-X','utf8',str(HERE/'persistent-worker.py'),'measure','--released','PACKAGE_READY',
        '--ready',str(a.ready.resolve()),'--dataset',str(derivative),'--connections',str(a.connections),'--variant',a.variant,
        '--output',str(output),'--samples','20','--warmup','3','--max-seconds','180']
    report=dict(status='STARTING',root=str(root),command=command,source_dataset_sha256=sha(source),source_seed_db_sha256=sha(seed/case['db_relative']),
                ready_sha256=sha(a.ready),worker_sha256=sha(HERE/'persistent-worker.py'),output=str(output))
    (root/'cwd').mkdir()
    started=time.monotonic()
    with (root/'stdout.txt').open('w')as stdout,(root/'stderr.txt').open('w')as stderr:
        child=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr)
        child.stdin.close();report['pid']=child.pid
        print(json.dumps(dict(pid=child.pid,root=str(root))),flush=True)
        try:report['exit_code']=child.wait(timeout=240)
        except subprocess.TimeoutExpired:
            report['timeout']=True;child.terminate()
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=15)
            report['exit_code']=child.returncode
    report.update(status='EXITED',seconds=time.monotonic()-started,physical_exit=child.poll()is not None,
                  source_dataset_drift=sha(source)!=report['source_dataset_sha256'],source_seed_drift=sha(seed/case['db_relative'])!=report['source_seed_db_sha256'])
    evidence.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    raise SystemExit(report['exit_code'])


if __name__=='__main__':main()
