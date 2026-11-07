
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
    if name in ('inbox_pull','inbox_ack'):
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
          'delivered_count','acknowledged','read_message_ids')
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
