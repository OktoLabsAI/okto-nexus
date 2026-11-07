"""AC03: two distributed MCP clients, real TCP, no model/native adapter.

Opt-in dependencies are explicit executable/package paths. Inspector's shipped
programmatic modules are used because its CLI forwards bearer headers in argv.
FastMCP uses its separate Python client/transport. The small drivers only select
calls and keep fixture credentials in memory; neither implements MCP or HTTP.
"""
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading

import pytest

from test_service_restart_contracts import RestartServer


INSPECTOR_DRIVER = r"""
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import readline from 'node:readline';
const input = readline.createInterface({input:process.stdin, terminal:false});
const lines = input[Symbol.asyncIterator]();
const config = JSON.parse((await lines.next()).value);
const root = config.inspector;
const load = p => import(pathToFileURL(p).href);
const sdkRoot = path.join(root, '..', 'sdk');
const info = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const sdkInfo = JSON.parse(fs.readFileSync(path.join(sdkRoot, 'package.json'), 'utf8'));
const {Client} = await load(path.join(sdkRoot, 'dist/esm/client/index.js'));
const {connect,disconnect,listTools,callTool} = await load(path.join(root,'cli/build/client/index.js'));
const {createTransport} = await load(path.join(root,'cli/build/transport.js'));
let client, transport, session;
const emit = value => process.stdout.write(JSON.stringify(value)+'\n');
const pick = (data,keys) => Object.fromEntries(keys.filter(k=>k in data).map(k=>[k,data[k]]));
function unwrapEnvelope(result) {
  const value=result.structuredContent || JSON.parse(result.content.find(c=>c.type==='text').text);
  if(result.isError || !value.ok) throw new Error('Canonical tool refused');
  return value.data;
}
async function open() {
  client = new Client({name:info.name,version:info.version});
  transport = createTransport({transportType:'http',url:config.url,
    headers:{Authorization:'Bearer '+config.token}});
  await connect(client,transport);
}
function publicData(name, data) {
  if(name === 'session_open') session = data;
  if(name === 'nexus_info') return pick(data,['coordination_requests','coordination_observation','coordination_cooperation']);
  if(name === 'event_cursor') return pick(data,['cursor']);
  if(name === 'event_wait') return pick(data,['next_cursor']);
  if(name === 'message_status') return {...pick(data,['message_id','count','replies_truncated']),
    deliveries:data.deliveries.map(d=>pick(d,['recipient','status'])),
    replies:data.replies.map(r=>pick(r,['message_id','parent_message_id','workspace_id','from_agent_id',
      'target','delivery_status','authority_kind','runtime_outcome','created_at','read_at']))};
  if(name === 'handoff_get') return pick(data,['handoff_id','workspace_id','from_agent_id','target',
    'status','claimed_by','claim_epoch','result']);
  if(name === 'inbox_pull') return {messages:data.messages.map(m => ({
    message_id:m.message_id,from_agent_id:m.from_agent_id,parent_message_id:m.parent_message_id,
    workspace_id:m.workspace_id,body:m.body}))};
  const keys=['session_id','agent_id','workspace_id','status','message_id','recipients',
    'delivered_count','acknowledged','read_message_ids','handoff_id'];
  const value=pick(data,keys);
  if(['message_create','handoff_create','coordination_request_get'].includes(name) && data.request_receipt)
    value.request_receipt=pick(data.request_receipt,['server_id','actor_agent_id','workspace_id','operation',
      'client_request_id','state','resource_id','approval_id','created_at','expires_at']);
  return value;
}
function argsFor(name, args) {
  if(['inbox_pull','inbox_ack','handoff_create'].includes(name))
    return {...args,session_id:session.session_id,session_secret:session.session_secret};
  if(name === 'message_create')
    return {...args,from_session_id:session.session_id,session_secret:session.session_secret};
  if(['session_heartbeat','session_close'].includes(name))
    return {...args,session_id:session.session_id};
  return args;
}
try {
  if(config.probe) {
    emit({client:info.name,version:info.version,sdk:sdkInfo.version,
      api:[connect,disconnect,listTools,callTool,createTransport].every(x=>typeof x==='function')});
  } else {
    await open();
    emit({client:info.name,version:info.version,sdk:sdkInfo.version});
    for await (const line of lines) {
      const cmd=JSON.parse(line);
      try {
        if(cmd.method === 'stop') {await disconnect(transport);emit({ok:true});break;}
        if(cmd.method === 'reconnect') {await disconnect(transport);await open();emit({ok:true});continue;}
        if(cmd.method === 'list') {emit({ok:true,tools:(await listTools(client)).tools.map(t=>t.name)});continue;}
        if(cmd.method === 'discover') {
          const names=['message_create','handoff_create','coordination_request_get','message_status',
            'handoff_get','event_cursor','event_wait','nexus_info'];
          const tools=(await listTools(client)).tools.filter(t=>names.includes(t.name));
          const info=publicData('nexus_info',unwrapEnvelope(await callTool(client,'nexus_info',{})));
          emit({ok:true,data:{schemas:Object.fromEntries(tools.map(t=>[t.name,t.inputSchema])),info}});continue;
        }
        const result=await callTool(client,cmd.name,argsFor(cmd.name,cmd.args||{}));
        const envelope=result.structuredContent || JSON.parse(result.content.find(c=>c.type==='text').text);
        if(result.isError || !envelope.ok) {emit({ok:false,code:envelope.error?.code||'TOOL_FAILED'});continue;}
        emit({ok:true,data:publicData(cmd.name,envelope.data)});
      } catch (error) {emit({ok:false,code:'CLIENT_CALL_FAILED',type:error.constructor.name});}
    }
  }
} catch(error) {emit({ok:false,code:'CLIENT_START_FAILED',type:error.constructor.name});process.exitCode=1;}
finally {input.close(); if(transport) {try {await disconnect(transport);} catch {process.exitCode=1;}}}
"""


FASTMCP_DRIVER = r"""
import asyncio
import importlib.metadata
import json
import sys
config=json.loads(sys.stdin.readline())
# Explicit code/dependencies only; -I and the parent-owned synthetic HOME remain.
sys.path[:0]=config['dependency_paths']
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.client.auth import BearerAuth
from mcp.types import Implementation
version=importlib.metadata.version('fastmcp')
sdk=importlib.metadata.version('mcp')
session=None
def emit(value):
    print(json.dumps(value),flush=True)
def args_for(name,args):
    if name in ('inbox_pull','inbox_ack','handoff_claim','handoff_complete'):
        return dict(args,session_id=session['session_id'],session_secret=session['session_secret'])
    if name=='message_create':
        return dict(args,from_session_id=session['session_id'],session_secret=session['session_secret'])
    if name in ('session_heartbeat','session_close'):
        return dict(args,session_id=session['session_id'])
    return args
def public_data(name,data):
    global session
    if name=='session_open':
        session=data
    if name=='inbox_pull':
        return {'messages':[{k:m.get(k) for k in ('message_id','from_agent_id',
            'parent_message_id','workspace_id','body')} for m in data['messages']]}
    keys=('session_id','agent_id','workspace_id','status','message_id','recipients',
          'delivered_count','acknowledged','read_message_ids','handoff_id','claimed_by','claim_epoch','result')
    return {k:data[k] for k in keys if k in data}
def make_client():
    return Client(StreamableHttpTransport(config['url'],auth=BearerAuth(config['token'])),
        timeout=15,client_info=Implementation(name='fastmcp',version=version))
async def main():
    if config.get('probe'):
        emit(dict(client='fastmcp',version=version,sdk=sdk,
                  api=all(callable(x) for x in (Client.list_tools,Client.call_tool,StreamableHttpTransport))))
        return
    client=make_client()
    await client.__aenter__()
    emit(dict(client='fastmcp',version=version,sdk=sdk))
    try:
        while line:=await asyncio.to_thread(sys.stdin.readline):
            cmd=json.loads(line)
            try:
                if cmd['method']=='stop':
                    emit({'ok':True})
                    break
                if cmd['method']=='reconnect':
                    await client.__aexit__(None,None,None)
                    client=make_client()
                    await client.__aenter__()
                    emit({'ok':True})
                    continue
                if cmd['method']=='list':
                    emit(dict(ok=True,tools=[t.name for t in await client.list_tools()]))
                    continue
                result=await client.call_tool(cmd['name'],args_for(cmd['name'],cmd.get('args',{})))
                envelope=result.structured_content or json.loads(next(c.text for c in result.content if c.type=='text'))
                if result.is_error or not envelope.get('ok'):
                    emit(dict(ok=False,code=envelope.get('error',{}).get('code','TOOL_FAILED')))
                    continue
                emit(dict(ok=True,data=public_data(cmd['name'],envelope['data'])))
            except Exception as error:
                emit(dict(ok=False,code='CLIENT_CALL_FAILED',type=type(error).__name__))
    finally:
        await client.__aexit__(None,None,None)
try:
    asyncio.run(main())
except Exception as error:
    emit(dict(ok=False,code='CLIENT_START_FAILED',type=type(error).__name__))
    raise SystemExit(1) from None
"""


class ExistingClient:
    def __init__(self, root, kind, command, config, env):
        self.path = root / kind
        self.path.mkdir()
        env = dict(env, HOME=str(self.path), USERPROFILE=str(self.path), APPDATA=str(self.path),
                   LOCALAPPDATA=str(self.path), PYTHONDONTWRITEBYTECODE='1', FASTMCP_LOG_ENABLED='false')
        self.errors = (self.path / 'private-stderr.log').open('w', encoding='utf-8')
        self.process = subprocess.Popen(command, cwd=self.path, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.errors, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.lines = queue.Queue()
        def read():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self.send(config)  # Private stdin, never argv/env/file/log.
            self.identity = self.receive()
        except BaseException:
            self.abort()
            raise

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()

    def receive(self):
        try:
            line = self.lines.get(timeout=30)
        except queue.Empty:
            pytest.fail('Existing MCP client did not return a bounded response')
        assert line is not None, 'Existing MCP client exited; private stderr is excluded from public evidence'
        return json.loads(line)

    def request(self, method, name=None, **args):
        self.send(dict(method=method, name=name, args=args))
        result = self.receive()
        assert result.get('ok'), result  # Drivers expose only coded failures.
        return result.get('data', result)

    def close(self):
        try:
            if self.process.poll() is None:
                self.request('stop')
                self.process.stdin.close()
                self.process.wait(timeout=15)
            assert self.process.returncode == 0, 'Existing MCP client exited unsuccessfully'
        finally:
            self.abort()

    def abort(self):
        try:
            if self.process.poll() is None:
                self.process.kill()  # Only this fixture's Popen handle.
                self.process.wait(timeout=10)
        finally:
            self.reader.join(timeout=5)
            self.process.stdout.close()
            if not self.process.stdin.closed:
                self.process.stdin.close()
            self.errors.close()


def _dependencies():
    names = ('NEXUS_AC03_NODE', 'NEXUS_AC03_INSPECTOR_ROOT',
             'NEXUS_AC03_PYTHON', 'NEXUS_AC03_PYTHON_PATHS')
    values = {name: os.environ.get(name) for name in names}
    if not all(values.values()):
        pytest.skip('AC03 requires explicit installed Inspector/FastMCP dependency paths')
    paths = json.loads(values['NEXUS_AC03_PYTHON_PATHS'])
    assert isinstance(paths, list) and paths and all(Path(p).is_dir() for p in paths)
    for name in names[:3]:
        assert Path(values[name]).exists(), 'Configured client dependency is unavailable'
    return values, paths


def _canonical(server):
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        connection = uow.connection
        return {
            'agents': [r[0] for r in connection.execute('SELECT agent_id FROM agents ORDER BY agent_id')],
            'bindings': [tuple(r) for r in connection.execute('SELECT * FROM execution_bindings')],
            'runtime_sessions': connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0],
            'operations': connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0],
        }


def test_inspector_and_fastmcp_participate_and_reconnect_without_duplicate_identity(tmp_path):
    values, paths = _dependencies()
    from okto_nexus.application.auth import AgentKeyAuthService

    server = RestartServer(tmp_path)
    clients = []
    try:
        keys = {}
        auth = AgentKeyAuthService(server.deps.repos.agents, server.deps.clock)
        with server.deps.connection_factory.unit_of_work() as uow:
            server.deps.repos.workspaces.upsert(uow, workspace_id='ac03-workspace', display_name='AC03 synthetic workspace')
            for agent in ('ac03-inspector', 'ac03-fastmcp'):
                server.deps.repos.agents.upsert(uow, agent_id=agent, role='Synthetic MCP participant')
                keys[agent] = auth.issue_key(uow, agent_id=agent)
        server.start()
        before = _canonical(server)
        inspector_script = tmp_path / 'inspector-client.mjs'
        inspector_script.write_text(INSPECTOR_DRIVER, encoding='utf-8')
        fastmcp_script = tmp_path / 'fastmcp-client.py'
        fastmcp_script.write_text(FASTMCP_DRIVER, encoding='utf-8')
        inspector = ExistingClient(tmp_path, 'inspector', [values['NEXUS_AC03_NODE'], str(inspector_script)],
            dict(url=server.origin+'/mcp/', token=keys['ac03-inspector'], inspector=values['NEXUS_AC03_INSPECTOR_ROOT']), server.env)
        clients.append(inspector)
        fastmcp = ExistingClient(tmp_path, 'fastmcp', [values['NEXUS_AC03_PYTHON'], '-I', str(fastmcp_script)],
            dict(url=server.origin+'/mcp/', token=keys['ac03-fastmcp'], dependency_paths=paths), server.env)
        clients.append(fastmcp)
        assert inspector.identity == dict(client='@modelcontextprotocol/inspector', version='0.21.2', sdk='1.29.0')
        assert fastmcp.identity == dict(client='fastmcp', version='2.14.7', sdk='1.30.0')
        required = {'session_open','session_heartbeat','message_create','inbox_pull','inbox_ack'}
        sessions = {}
        for client, agent in zip(clients, ('ac03-inspector', 'ac03-fastmcp')):
            assert required <= set(client.request('list')['tools'])
            sessions[agent] = client.request('call', 'session_open', agent_id=agent, workspace_id='ac03-workspace')['session_id']
        def presence():
            with server.deps.connection_factory.unit_of_work(write=False) as uow:
                return [tuple(r) for r in uow.connection.execute(
                    'SELECT agent_id,session_id,workspace_id,status FROM sessions ORDER BY agent_id')]
        expected = [(agent, sessions[agent], 'ac03-workspace', 'active') for agent in sorted(sessions)]
        assert presence() == expected
        sent = inspector.request('call', 'message_create', from_agent_id='ac03-inspector',
            workspace_id='ac03-workspace', target={'strategy':'direct','agent_id':'ac03-fastmcp'},
            subject='AC03 directed exchange', body='Synthetic request', client_request_id='ac03-directed-request')
        mid = sent['message_id']
        received = fastmcp.request('call', 'inbox_pull', agent_id='ac03-fastmcp')['messages']
        assert [m['message_id'] for m in received] == [mid]
        assert received[0]['from_agent_id'] == 'ac03-inspector' and received[0]['body'] == 'Synthetic request'
        fastmcp.request('call', 'inbox_ack', agent_id='ac03-fastmcp', message_ids=[mid])
        reply = fastmcp.request('call', 'message_create', from_agent_id='ac03-fastmcp',
            workspace_id='ac03-workspace', target={'strategy':'direct','agent_id':'ac03-inspector'},
            parent_message_id=mid, subject='AC03 directed reply', body='Synthetic reply', client_request_id='ac03-directed-reply')
        inbox = inspector.request('call', 'inbox_pull', agent_id='ac03-inspector')['messages']
        correlated = [m for m in inbox if m['message_id'] == reply['message_id']]
        assert len(correlated) == 1
        assert correlated[0]['from_agent_id'] == 'ac03-fastmcp' and correlated[0]['body'] == 'Synthetic reply'
        inspector.request('call', 'inbox_ack', agent_id='ac03-inspector', message_ids=[reply['message_id']])
        for client in clients:
            client.request('reconnect')
            heartbeat = client.request('call', 'session_heartbeat', workspace_id='ac03-workspace')
            assert heartbeat['status'] == 'active'
            assert required <= set(client.request('list')['tools'])
        assert presence() == expected  # Same useful sessions, no reopening or new identities.
        assert _canonical(server) == before
        assert before['runtime_sessions'] == before['operations'] == 0
        with server.deps.connection_factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute('SELECT message_id,from_agent_id,parent_message_id,workspace_id FROM messages '
                'WHERE message_id IN (?,?) ORDER BY message_id', (mid,reply['message_id'])).fetchall()
            assert len(rows) == 2 and all(r['workspace_id'] == 'ac03-workspace' for r in rows)
            by_id = {r['message_id']: r for r in rows}
            assert by_id[mid]['from_agent_id'] == 'ac03-inspector' and by_id[mid]['parent_message_id'] is None
            assert by_id[reply['message_id']]['from_agent_id'] == 'ac03-fastmcp'
            assert by_id[reply['message_id']]['parent_message_id'] == mid
            assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        evidence = dict(clients=[c.identity for c in clients], sessions=sessions,
            message_ids=[mid,reply['message_id']], reconnect_same_sessions=True,
            identity_and_bindings_unchanged=True, runtime_operations=0, native_adapters_added=0,
            qualification='Existing programmatic Inspector and FastMCP over real TCP; no model, vault or CLI-header claim.',
            drivers={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (inspector_script,fastmcp_script)})
        (tmp_path/'public-client-proof.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        for client in clients:
            client.close()
        clients.clear()
        server.stop()
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1',server.port)) != 0
    finally:
        cleanup_errors = []
        for client in clients:
            try:
                client.close()
            except BaseException as error:
                cleanup_errors.append(error)
        try:
            server.cleanup()
        except BaseException as error:
            cleanup_errors.append(error)
        if cleanup_errors:
            raise BaseExceptionGroup('Owned AC03 cleanup failures', cleanup_errors)
