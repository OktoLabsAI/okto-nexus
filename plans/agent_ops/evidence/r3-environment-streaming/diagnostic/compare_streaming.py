"""Read-only alternative snapshot algorithm; not an installed patch or probe."""
import hashlib,json,sys,time
from pathlib import Path
from importlib import metadata

HERE=Path(__file__).resolve().parent
W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
FILE_LIMIT=64*1024*1024
TOTAL_LIMIT=256*1024*1024
CHUNK=64*1024

def main():
    assert sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.utf8_mode
    assert Path(sys.executable).resolve()==(W/'package/venv/Scripts/python.exe').resolve()
    from okto_nexus import service_environment as module
    original=module._distribution;stages=[]
    def streaming(name,package):
        wall=time.monotonic();cpu=time.process_time()
        distribution=metadata.distribution(name)
        direct=distribution.read_text('direct_url.json')
        if direct and json.loads(direct).get('dir_info',{}).get('editable'):raise ValueError('editable refused')
        paths=sorted(distribution.files or (),key=str)
        if len(paths)>10000 or not any(str(p).replace('\\','/').startswith(package+'/') and str(p).endswith('.py') for p in paths):raise ValueError('payload invalid')
        digest=hashlib.sha256();total=0;files=0;reads=0;open_wall=0.;read_wall=0.;hash_wall=0.;max_return=0
        for item in paths:
            relative=str(item).replace('\\','/')
            if '__pycache__/' in relative or relative.endswith(('.pyc','.pyo')):continue
            path=Path(distribution.locate_file(item));file_bytes=0;file_digest=hashlib.sha256()
            start=time.monotonic();stream=path.open('rb');open_wall+=time.monotonic()-start
            with stream:
                while True:
                    start=time.monotonic();chunk=stream.read(min(CHUNK,FILE_LIMIT+1-file_bytes));read_wall+=time.monotonic()-start
                    reads+=1;max_return=max(max_return,len(chunk))
                    if not chunk:break
                    file_bytes+=len(chunk);total+=len(chunk)
                    if file_bytes>FILE_LIMIT or total>TOTAL_LIMIT:raise ValueError('byte budget exceeded')
                    start=time.monotonic();file_digest.update(chunk);hash_wall+=time.monotonic()-start
            digest.update(relative.encode('utf-8')+b'\0'+file_digest.digest());files+=1
        stages.append({'distribution':name,'files':files,'payload_bytes':total,'read_calls':reads,
            'maximum_returned_chunk_bytes':max_return,'open_wall_seconds':open_wall,'read_wall_seconds':read_wall,
            'hash_wall_seconds':hash_wall,'elapsed_wall_seconds':time.monotonic()-wall,'elapsed_cpu_seconds':time.process_time()-cpu})
        return {'version':distribution.version,'digest':digest.hexdigest()}
    wall=time.monotonic();cpu=time.process_time()
    try:module._distribution=streaming;snapshot=module.snapshot()
    finally:module._distribution=original
    elapsed=time.monotonic()-wall;cpu_elapsed=time.process_time()-cpu
    candidate=json.loads((W/'private/environment-upgrade-plan.json').read_bytes())['plan']['candidate']
    result={'mode':'READONLY_EQUIVALENT_STREAMING_SNAPSHOT','installed_sources_changed':False,
        'matches_reviewed_candidate':snapshot==candidate,'elapsed_wall_seconds':elapsed,'elapsed_cpu_seconds':cpu_elapsed,
        'chunk_bytes':CHUNK,'per_file_limit_bytes':FILE_LIMIT,'oversize_detection_limit_bytes':FILE_LIMIT+1,
        'aggregate_limit_bytes':TOTAL_LIMIT,'file_count_limit':10000,'digest_algorithm':'sorted relative name + NUL + SHA256(full file bytes), aggregate SHA256',
        'snapshot_sha256':hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'stages':stages,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'service_or_provider_started':False,'canonical_probe60_success_claimed':False,
        'limitation':'In-memory diagnostic algorithm substitution only; no installed source change, no upgrade retry authority.'}
    with (HERE/'streaming-result.json').open('x',encoding='utf-8',newline='\n') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
