"""Canonical fixture controls, inert until explicitly called after READY.

Keys/cookies/passwords stay in memory/private Temp. No SQL writes or contextvar
impersonation. The TestClient must belong to this own installed application.
"""
import json
import os
from pathlib import Path
import secrets
import sqlite3
from contextlib import contextmanager


class Controls:
    def __init__(self, deps, app, client, root, reference, *, record):
        self.deps,self.app,self.client=deps,app,client
        self.root=Path(root).resolve()
        assert self.root.name.startswith('nexus-hst-')
        assert Path(deps.config.home_dir).resolve().is_relative_to(self.root)
        self.reference=dict(reference)
        self.record=record
        self._browser_cookie=None
        self._mcp_id=0

    def request(self, method, path, body=None, *, headers=None):
        response=self.client.request(method,path,json=body,headers=headers or {'X-Nexus-UI':'1'})
        self.record(dict(method=method,path=path.split('?')[0],status=response.status_code))
        if response.status_code>=400:
            value=response.json()
            raise RuntimeError('Canonical fixture request refused: '+str(response.status_code)+' '+str(value.get('error',{}).get('code','UNKNOWN')))
        value=response.json()
        return value.get('data',value)

    def mcp(self,key,name,arguments):
        self._mcp_id+=1
        response=self.client.post('/mcp/',headers={'x-api-key':key,'Cookie':'','Accept':'application/json, text/event-stream'},
            json=dict(jsonrpc='2.0',id=self._mcp_id,method='tools/call',params=dict(name=name,arguments=arguments)))
        self.record(dict(method='POST',path='/mcp/',tool=name,status=response.status_code))
        assert response.status_code==200,'MCP transport refused'
        value=json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: '))) if 'text/event-stream'in response.headers.get('content-type','') else response.json()
        assert 'result'in value,'MCP result absent'
        result=value['result'].get('structuredContent') or json.loads(value['result']['content'][0]['text'])
        if result.get('ok') is not True:
            error=result.get('error',{})
            diagnostic=dict(tool=name,code=error.get('code'),message=error.get('message'),reason=(error.get('details') or {}).get('reason'))
            self.record(dict(mcp_refusal=diagnostic))
            raise RuntimeError('MCP use case refused: '+json.dumps(diagnostic))
        return result['data']

    def prepare_handoff(self,creator_key,creator_id,worker_id):
        """Creator is a real synthetic agent, verifier is actual operator."""
        return self.mcp(creator_key,'handoff_create',dict(workspace_id=self.reference['workspace_id'],
            from_agent_id=creator_id,target=dict(strategy='direct',agent_id=worker_id),visibility='public',
            payload='HST governed fixture review',acceptance_criteria=['Fixture result marker is present'],
            verify_by=dict(kind='agent',agent_id='operator')))

    def prepare_work_grant(self,worker_id):
        from okto_nexus.domain.base import iso_plus
        # Explicit pre-browser authorization, not renewal by connect/resume.
        return self.request('POST','/api/v1/harness/grants',dict(actor_agent_id=worker_id,
            endpoint_id=self.reference['endpoint_id'],actions=['execute_work'],max_executions=1,
            expires_at=iso_plus(self.deps.clock.now_iso(),600)))

    def claim_handoff(self,worker_key,worker_id,handoff_id,grant_id):
        endpoints=self.request('GET','/api/v1/harness/endpoints?agent_id='+worker_id)
        rows=endpoints if isinstance(endpoints,list) else endpoints.get('items',[])
        endpoint=next(row for row in rows if row['endpoint_id']==self.reference['endpoint_id'])
        assert endpoint['consumption']=='exclusive','Do not patch SQL or silently change endpoint policy'
        return self.mcp(worker_key,'handoff_claim',dict(workspace_id=self.reference['workspace_id'],
            handoff_id=handoff_id,agent_id=worker_id,runtime_endpoint_id=self.reference['endpoint_id'],
            execution_grant_id=grant_id,idempotency_key='hst-work-'+secrets.token_hex(8),
            completion_mode='authenticated_nexus_call'))

    def verify_handoff(self,handoff_id,claim_epoch):
        # No agent key for operator. Domain must authorize operator verify_by.
        return self.request('POST','/api/v1/workspaces/'+self.reference['workspace_id']+'/handoffs/'+handoff_id+'/verify',
            dict(verdict='pass',claim_epoch=claim_epoch),headers=self.operator_headers())

    def complete_handoff(self,worker_key,worker_id,handoff_id,claim_epoch):
        return self.mcp(worker_key,'handoff_complete',dict(workspace_id=self.reference['workspace_id'],
            handoff_id=handoff_id,agent_id=worker_id,claim_epoch=claim_epoch,result='HST fixture governed result'))

    def handoff_state(self,key,actor,handoff_id):
        value=self.mcp(key,'handoff_get',dict(workspace_id=self.reference['workspace_id'],handoff_id=handoff_id,agent_id=actor))
        return {name:value.get(name) for name in ['handoff_id','status','claim_epoch','claimed_by']}

    def operator_headers(self):
        if self._browser_cookie:
            return {'X-Nexus-UI':'1','X-Nexus-Operator-Session-Required':'1','Cookie':'nexus_operator_session='+self._browser_cookie}
        return {'X-Nexus-UI':'1'}

    def configure_browser_session(self):
        auth=self.app.state.operator_auth
        assert Path(auth.path).resolve().is_relative_to(self.root)
        assert not auth.configured(),'Never replace existing credentials'
        password=secrets.token_urlsafe(32)
        self.request('POST','/api/v1/operator-auth/account',dict(username='hst-fixture',password=password))
        response=self.client.post('/api/v1/operator-auth/login',headers={'X-Nexus-UI':'1'},json=dict(username='hst-fixture',password=password))
        self.record(dict(method='POST',path='/api/v1/operator-auth/login',status=response.status_code))
        assert response.status_code==200
        self._browser_cookie=response.cookies.get('nexus_operator_session')
        assert self._browser_cookie and auth.resolve(self._browser_cookie)=='hst-fixture'
        return dict(authenticated=True,identity='own-human-session',requires_header=True)

    def write_private_storage(self,port):
        assert self._browser_cookie
        path=self.root/'control/browser-storage.private.json'
        value=dict(cookies=[dict(name='nexus_operator_session',value=self._browser_cookie,domain='127.0.0.1',
            path='/api/v1',httpOnly=True,secure=False,sameSite='Strict')],origins=[])
        path.write_text(json.dumps(value),encoding='utf-8');os.chmod(path,0o600)
        return path

    def revoke_browser_session(self):
        assert self._browser_cookie
        result=self.request('POST','/api/v1/operator-auth/logout',headers=self.operator_headers())
        assert self.app.state.operator_auth.resolve(self._browser_cookie) is None
        self._browser_cookie=None
        return result

    def revoke_grant(self,grant_id):
        """Explicit own grant revoke. Does not imply operator read revocation."""
        return self.request('DELETE','/api/v1/harness/grants/'+grant_id,headers=self.operator_headers())

    @contextmanager
    def unavailable_results(self):
        queries=self.app.state.home_entries.queries
        original=queries._results
        def unavailable(*args,**kwargs):raise sqlite3.OperationalError('Own fixture results source unavailable')
        queries._results=unavailable
        try:yield
        finally:queries._results=original
