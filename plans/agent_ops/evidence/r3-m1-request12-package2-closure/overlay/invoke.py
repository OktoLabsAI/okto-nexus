"""Own once-only reentry ledger; original failed invocation remains untouched."""
from pathlib import Path
import json,subprocess,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from entry import load,parser

def main():
    args=parser().parse_args();context,m=load(args);common=context.common
    directory=common.secure_directory(HERE/'runtime-private',HERE)
    label='work-local-'+args.phase
    common.reserve(directory/(label+'.reserved.json'),{**common.tags(context),'phase':args.phase,
        'manifest_sha256':args.expected_manifest_sha256,'original_failed_wrapper':m['basis']['failed_wrapper'],
        'selected_at':time.time(),'state':'DISPATCH_RESERVED','model_reservation_added_by_invoker':False})
    argv=[context.installed['python'],'-X','utf8','-I','-B',str(HERE/'entry.py'),
        '--manifest',args.manifest,'--expected-manifest-sha256',args.expected_manifest_sha256,args.phase]
    with (directory/(label+'.stdout')).open('xb') as stdout,(directory/(label+'.stderr')).open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=context.ROOT,env=context.env(),stdin=subprocess.DEVNULL,
            stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        common.reserve(directory/(label+'.process.json'),{'pid':child.pid,'phase':args.phase,
            'manifest_sha256':args.expected_manifest_sha256})
        code=child.wait()
    result={**common.tags(context),'phase':args.phase,'manifest_sha256':args.expected_manifest_sha256,
        'returncode':code,'wrapper_exit_confirmed':True,'completed_at':time.time(),
        'stdout_sha256':common.sha(directory/(label+'.stdout')),'stderr_sha256':common.sha(directory/(label+'.stderr')),
        'original_failed_wrapper_sha256':m['basis']['failed_wrapper']['sha256'],'original_failure_reclassified':False}
    common.reserve(directory/(label+'.returned.json'),result);print(json.dumps(result));return code
if __name__=='__main__':raise SystemExit(main())
