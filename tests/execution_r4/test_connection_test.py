"""Draft probes require correlated output, terminal success and contained cleanup."""
import asyncio
from types import SimpleNamespace
import pytest
from okto_nexus.application import connection_test as module


@pytest.mark.parametrize('outcome,text,cleanup,expected',[
    ('success','NEXUS_CONNECTION_OK','already_closed','succeeded'),
    ('success','','already_closed','failed'),
    ('failed','NEXUS_CONNECTION_OK','already_closed','failed'),
    ('success','NEXUS_CONNECTION_OK','unknown','failed'),
])
def test_probe_requires_output_and_cleanup(tmp_path,monkeypatch,outcome,text,cleanup,expected):
    observed={}
    class Journal:
        def __init__(self,*a):pass
        async def get_receipt(self,key):return SimpleNamespace(stage='SUCCEEDED' if outcome=='success' else 'FAILED')
        def close(self):observed['journal_closed']=True
    class Runtime:
        def __init__(self,*a,**k): self.shutdowns=0
        async def prepare(self,intent,context):observed['intent']=intent;return object()
        async def open(self,*a):return SimpleNamespace(stage='SUBMITTED')
        async def submit(self,*a):pass
        async def events(self,*a):
            yield SimpleNamespace(operation_id='turn',category='text_delta',payload={'output_text':text})
            yield SimpleNamespace(operation_id='turn',category='turn_state',payload={'delivery_phase':'terminal','delivery_outcome':outcome})
        async def close(self,*a):observed['closed']=True
        async def shutdown(self,*a):
            self.shutdowns+=1
            return SimpleNamespace(session_outcomes={'session':cleanup if self.shutdowns==1 else 'already_closed'})
    monkeypatch.setattr(module,'SQLiteJournal',Journal)
    monkeypatch.setattr(module,'LocalRuntimeCore',Runtime)
    deps=SimpleNamespace(config=SimpleNamespace(home_dir=tmp_path))
    manager=module.ConnectionTests(deps)
    entry=dict(status='running',details=[])
    request=dict(agent_id='agent',configuration=dict(adapter_id='pi_rpc',workspace_root=str(tmp_path),provider_home=None,
        secret_bindings={},harness_settings={'model':'glm-5.3','provider':'zai','effort':'low'}))
    request['mcp_preset'] = dict(expected_revision=0, servers=[
        dict(name='docs', transport='http', url='https://example.test/mcp')])
    asyncio.run(manager.run(entry,request,object()))
    assert entry['status']==expected
    assert observed['journal_closed']
    assert observed['intent'].model=='glm-5.3'
    assert observed['intent'].harness_settings.provider=='zai'
    assert observed['intent'].mcp_preset == tuple(request['mcp_preset']['servers'])
