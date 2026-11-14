"""Measure the selected installed snapshot without changing its read algorithm."""
import hashlib,json,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
PREFIX=W/'package/venv'

def main():
    assert sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.utf8_mode
    assert Path(sys.executable).resolve()==(PREFIX/'Scripts/python.exe').resolve()
    from okto_nexus import service_environment as module
    original_open=Path.open;original_sha=hashlib.sha256;original_distribution=module._distribution
    records=[];hash_wall=0.;hash_cpu=0.;hash_bytes=0;stages=[]
    def memory():
        try:
            import psutil
            info=psutil.Process().memory_info()
            return {k:getattr(info,k) for k in ('rss','vms','peak_wset') if hasattr(info,k)}
        except ImportError:return {'available':False}
    class Stream:
        def __init__(self,stream,record):self.stream,self.record=stream,record
        def __enter__(self):self.stream.__enter__();return self
        def __exit__(self,*args):return self.stream.__exit__(*args)
        def __getattr__(self,key):return getattr(self.stream,key)
        def read(self,size=-1):
            wall=time.monotonic();cpu=time.process_time()
            value=self.stream.read(size)
            self.record['read_wall_seconds']+=time.monotonic()-wall
            self.record['read_cpu_seconds']+=time.process_time()-cpu
            self.record['requested_bytes']=size;self.record['returned_bytes']+=len(value)
            return value
    def measured_open(path,*args,**kwargs):
        mode=args[0] if args else kwargs.get('mode','r')
        if mode!='rb' or not Path(path).is_relative_to(PREFIX):return original_open(path,*args,**kwargs)
        wall=time.monotonic();cpu=time.process_time();stream=original_open(path,*args,**kwargs)
        record={'file':str(Path(path).relative_to(PREFIX)),'open_wall_seconds':time.monotonic()-wall,
            'open_cpu_seconds':time.process_time()-cpu,'read_wall_seconds':0.,'read_cpu_seconds':0.,'returned_bytes':0}
        records.append(record)
        return Stream(stream,record)
    def measured_sha(data=b'',*args,**kwargs):
        nonlocal hash_wall,hash_cpu,hash_bytes
        wall=time.monotonic();cpu=time.process_time();value=original_sha(data,*args,**kwargs)
        hash_wall+=time.monotonic()-wall;hash_cpu+=time.process_time()-cpu;hash_bytes+=len(data)
        return value
    def measured_distribution(name,package):
        wall=time.monotonic();cpu=time.process_time();start=len(records)
        value=original_distribution(name,package)
        group=records[start:]
        stage={'distribution':name,'elapsed_wall_seconds':time.monotonic()-wall,'elapsed_cpu_seconds':time.process_time()-cpu,
            'files':len(group),'payload_bytes':sum(r['returned_bytes'] for r in group),'memory':memory()}
        stages.append(stage);print(json.dumps({'stage_completed':stage}),flush=True)
        return value
    memory_before=memory();wall=time.monotonic();cpu=time.process_time()
    try:
        Path.open=measured_open;hashlib.sha256=measured_sha;module._distribution=measured_distribution
        snapshot=module.snapshot()
    finally:
        Path.open=original_open;hashlib.sha256=original_sha;module._distribution=original_distribution
    elapsed=time.monotonic()-wall;cpu_elapsed=time.process_time()-cpu
    plan=json.loads((W/'private/environment-upgrade-plan.json').read_bytes())
    fields=('open_wall_seconds','open_cpu_seconds','read_wall_seconds','read_cpu_seconds','returned_bytes')
    result={'mode':'ORIGINAL_SNAPSHOT_INSTRUMENTED','algorithm_changed':False,'matches_reviewed_candidate':snapshot==plan['plan']['candidate'],
        'elapsed_wall_seconds':elapsed,'elapsed_cpu_seconds':cpu_elapsed,'file_reads':len(records),
        'totals':{k:sum(r[k] for r in records) for k in fields},'hash_wall_seconds':hash_wall,'hash_cpu_seconds':hash_cpu,'hash_bytes':hash_bytes,
        'read_size_limit_64MiB_calls':sum(r.get('requested_bytes')==64*1024*1024+1 for r in records),
        'memory_before':memory_before,'memory_after':memory(),'stages':stages,
        'slowest_ten_reads':sorted(records,key=lambda r:r['open_wall_seconds']+r['read_wall_seconds'],reverse=True)[:10],
        'services_started':False,'provider_accessed':False,'source_sha256':original_sha(Path(__file__).read_bytes()).hexdigest()}
    with (HERE/'profile-result.json').open('x',encoding='utf-8',newline='\n') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
