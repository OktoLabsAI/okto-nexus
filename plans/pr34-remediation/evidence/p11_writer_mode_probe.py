+"""Diagnostic reproduction, not an acceptance PASS. Uses disposable synthetic peers only."""
import sys,tempfile,json,asyncio,logging
from pathlib import Path
from types import SimpleNamespace
logging.disable(logging.CRITICAL)
sys.path.insert(0,str(Path("tests").resolve()))
from test_pr34_remediation import runtime,open_rest,stdio_environment
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
fixture=runtime.__wrapped__(Path(tempfile.mkdtemp(prefix="okto-writer-audit-")),SimpleNamespace(param=True))
rt=next(fixture)
try:
    deps,client,root,peers,operator,caller=rt
    assert open_rest(rt).status_code==200
    async def create():
        params=StdioServerParameters(command=sys.executable,args=["-m","okto_nexus.adapters.inbound.mcp.server","--home",str(deps.config.home_dir),"--feature-harness-integrations","false"],env=stdio_environment(rt))
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                await session.initialize()
                response=await session.call_tool("message_create",{"project_root":root,"from_agent_id":"caller","subject":"writer audit","body":"disposable fixture only","target":{"strategy":"direct","agent_id":"worker"}})
                return response.structuredContent or json.loads(response.content[0].text)
    response=asyncio.run(asyncio.wait_for(create(),timeout=30))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        deliveries=[dict(row) for row in uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries")]
        outbox=uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0]
    report={"sha":"feeb14d","probe":"authenticated feature-OFF stdio writer against active feature-ON owner","request_ok":response["ok"],"deliveries":deliveries,"outbox_count":outbox,"fake_peer_send_count":sum(len(peer.sent) for peer in peers)}
    Path("plans/pr34-remediation/evidence/p11-writer-mode-audit.json").write_text(json.dumps(report,indent=2)+chr(10),encoding="utf-8")
    print(json.dumps(report))
finally:
    fixture.close()
