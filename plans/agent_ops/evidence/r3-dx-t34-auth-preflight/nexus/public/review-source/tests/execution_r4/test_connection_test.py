"""Draft probes require correlated output, terminal success and contained cleanup."""
import asyncio
from types import SimpleNamespace
import pytest
import test_local_realization
from okto_nexus.application import connection_test as module

local_setup = test_local_realization.local_setup


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
    async def run_test():
        entry['task'] = asyncio.create_task(manager.run(entry,request,object()))
        await entry['task']
    asyncio.run(run_test())
    assert entry['status']==expected
    assert observed['journal_closed']
    assert manager.public(entry | {'test_id': 'synthetic'})['retryable_failure'] is (expected == 'failed')
    assert observed['intent'].model=='glm-5.3'
    assert observed['intent'].harness_settings.provider=='zai'
    assert observed['intent'].mcp_preset == tuple(request['mcp_preset']['servers'])


@pytest.mark.parametrize('local_setup',['claude_stream','codex_app_server'],indirect=True)
def test_null_provider_home_fails_fast_only_for_claude(local_setup):
    from test_connection_setup import request_for
    context,request=request_for(local_setup)
    client,headers=local_setup[2:4]
    path='/api/v1/runtime-management/connections/setup:test'
    claude=request['configuration']['adapter_id']=='claude_stream'
    response=client.post(path,headers=headers['operator'],json=request)
    if claude:
        assert response.status_code==422,response.text
        assert 'provider_home' in response.json()['error']['message']
        assert not local_setup[1].state.connection_tests.tests
    else:
        assert response.status_code==200,response.text
        assert request['configuration']['provider_home'] is None


@pytest.mark.parametrize('failure_at', ['open', 'submit', 'terminal', 'exception'])
@pytest.mark.parametrize('code', ['PROVIDER_AUTH_REQUIRED', 'NATIVE_PROTOCOL_INCOMPATIBLE'])
def test_probe_preserves_provider_auth_cause_and_contains_cleanup(tmp_path, monkeypatch, failure_at, code):
    calls = []
    class Journal:
        def __init__(self, *args): pass
        async def get_receipt(self, key):
            return SimpleNamespace(stage='FAILED', error_code=code)
        def close(self): calls.append('journal.close')
    class Runtime:
        def __init__(self, *args, **kwargs): pass
        async def prepare(self, *args): return object()
        async def open(self, *args):
            calls.append('open')
            if failure_at == 'exception':
                raise module.CoreError(code, 'fixture', possible_effect=True, retry_safe=False)
            return SimpleNamespace(stage='FAILED' if failure_at == 'open' else 'SUBMITTED', error_code=code)
        async def submit(self, *args):
            calls.append('submit')
            return SimpleNamespace(stage='FAILED' if failure_at == 'submit' else 'SUBMITTED', error_code=code)
        async def events(self, *args):
            calls.append('events')
            yield SimpleNamespace(operation_id='turn', category='turn_state',
                payload={'delivery_phase': 'terminal', 'delivery_outcome': 'failed', 'diagnostic': 'secret-fixture-must-not-escape'})
        async def shutdown(self, *args):
            calls.append('shutdown')
            return SimpleNamespace(session_outcomes={'session': 'already_closed'})
    monkeypatch.setattr(module, 'SQLiteJournal', Journal)
    monkeypatch.setattr(module, 'LocalRuntimeCore', Runtime)
    manager = module.ConnectionTests(SimpleNamespace(config=SimpleNamespace(home_dir=tmp_path)))
    entry = dict(status='running', details=[])
    request = dict(agent_id='agent', configuration=dict(adapter_id='pi_rpc', workspace_root=str(tmp_path),
        provider_home=None, secret_bindings={}, harness_settings={}))
    asyncio.run(manager.run(entry, request, object()))
    expected = code if code == 'PROVIDER_AUTH_REQUIRED' or failure_at == 'exception' else (
        'CONNECTION_FAILED' if failure_at == 'open' else 'MODEL_RESPONSE_FAILED')
    assert entry['status'] == 'failed' and entry['details'][-1] == expected
    assert entry['cleanup_confirmed'] and calls[-2:] == ['shutdown', 'journal.close']
    assert calls.count('open') == 1
    assert calls.count('submit') == (0 if failure_at in ('open', 'exception') else 1)
    assert calls.count('events') == (1 if failure_at == 'terminal' else 0)
    assert 'secret-fixture' not in str(entry)
