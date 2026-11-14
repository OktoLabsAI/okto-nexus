"""Exact frozen workflow -> entry translation -> actual cohort argparse, without effects."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys,tempfile
H=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
sys.path.insert(0,str(H))
import request_context,request_entry,cohort
workflow=json.loads((H/'workflow.json').read_bytes())
amendment=json.loads((H/'amendment.json').read_bytes())
step=next(s for s in workflow['steps'] if s['label']=='cleanup-proof')
argv=step['argv'];index=argv.index(str(H/'request_entry.py'))
args,remaining=request_context.parser().parse_known_args(argv[index+1:])
assert remaining==['cleanup','nexus']
assert args.expected_amendment_sha256==hashlib.sha256((H/'amendment.json').read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='m1-cleanup-parser-fixture-') as folder:
    public=Path(folder);(public/'root-driver-preparation.json').write_text('{}')
    context=SimpleNamespace(PUBLIC=public,modules=H/'modules',amendment=amendment,
        P={'execution_bundle':{'files':amendment['bundle_overrides']}},
        common_args=lambda:argv[index+1:-2])
    calls=[]
    # The real request_context.gate installs this parser before importing cohort.
    cohort.parser=request_context.parser
    cohort.gate=lambda _:context
    cohort.cleanup=lambda selected:calls.append(selected) or {'fixture_cleanup_parser_selected':True}
    def run(path,run_name):
        assert Path(path)==H/'cohort.py' and run_name=='__main__'
        assert sys.argv[-2:]==['nexus','cleanup']
        assert cohort.main()==0
    assert request_entry.execute(context,remaining[0],remaining[1:],run=run)==0
    assert calls==[context]
print(json.dumps({'passed':1,'frozen_sources_changed':False,'real_cleanup_called':False,
    'exact_workflow_argv_parsed':True,'entry_translation':['nexus','cleanup']}))
