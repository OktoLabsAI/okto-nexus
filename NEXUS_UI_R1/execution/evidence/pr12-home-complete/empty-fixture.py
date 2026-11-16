"""Canonical zero-agent/zero-occurrence home; no runtime lifespan/provider."""
import argparse,asyncio,importlib.util,tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('ui12emptybase',ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ready-file',type=Path,required=True);parser.add_argument('--stop-file',type=Path,required=True);parser.add_argument('--expected-bundle',required=True);parser.add_argument('--duration',type=int,default=180);args=parser.parse_args()
    if not 30<=args.duration<=300:parser.error('finite30..300s required')
    home=Path(tempfile.mkdtemp(prefix='nexus-ui12-zero-'))
    deps=bootstrap({},['--home',str(home),'--embedding-mode','off','--metrics-mode','disabled'])
    deps.config.feature_observations=True
    try:
        with deps.connection_factory.unit_of_work() as uow:deps.repos.workspaces.upsert(uow,workspace_id='ws')
        asyncio.run(base.serve(SimpleNamespace(app=build_app(deps)),args,home,{'empty_zero_admission':True}))
    finally:deps.connection_factory.close()
    print('CLOSED: zero-admission factory normally',flush=True)
if __name__=='__main__':main()
