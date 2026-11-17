"""Own read-only navigation cut, reusing PR04 canonical SQLite/WSS facts."""
from pathlib import Path
import importlib.util
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
path=ROOT/'NEXUS_UI_R1/execution/evidence/pr04-browser/fixture.py'
spec=importlib.util.spec_from_file_location('ui07_navigation_base',path)
base=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=base
spec.loader.exec_module(base)
original_seed=base.seed
original_temporary=base.tempfile.mkdtemp


def seed(s):
    s.deps.config.feature_memory=False
    return original_seed(s)|{'memory_enabled':False,'navigation_read_only':True}


def temporary(*args,**kwargs):
    if kwargs.get('prefix')=='nexus-ui04-browser-':
        kwargs={**kwargs,'prefix':'nexus-ui07-navigation-'}
    return original_temporary(*args,**kwargs)


if __name__=='__main__':
    base.seed=seed
    base.tempfile.mkdtemp=temporary
    base.main()
