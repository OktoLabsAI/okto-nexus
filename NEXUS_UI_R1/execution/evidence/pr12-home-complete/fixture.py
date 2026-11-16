"""Own canonical idle connection plus single-source failure control."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('ui12controlled',ROOT/'NEXUS_UI_R1/execution/evidence/pr10-home-fences/fixture.py')
controlled=importlib.util.module_from_spec(spec);spec.loader.exec_module(controlled)
base=controlled.base;original=base.seed
def seed(s):
    ids=original(s)
    with s.factory.unit_of_work() as uow:
        c=uow.connection
        endpoint=c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ui-ep-2'").fetchone()
        base.fixtures._copy(c,'agent_endpoints',endpoint,endpoint_id='ui12-idle-endpoint')
        binding=c.execute("SELECT * FROM execution_bindings WHERE binding_id='ui-binding-2'").fetchone()
        base.fixtures._copy(c,'execution_bindings',binding,binding_id='ui12-idle-binding',endpoint_id='ui12-idle-endpoint')
        assert c.execute("SELECT count(*) FROM execution_sessions WHERE binding_id='ui12-idle-binding'").fetchone()[0]==0
    return dict(ids,idle_binding='ui12-idle-binding')
base.seed=seed
if __name__=='__main__':base.main()
