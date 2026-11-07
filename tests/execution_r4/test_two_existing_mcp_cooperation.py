"""DX08: consented facade smoke through two existing client implementations.

The Inspector's distributed transport performs facade calls; FastMCP is the
external peer. No provider, new adapter or client credential launcher is used.
The canonical handoff result is synthetic and explicitly consented by the test.
"""
from contextlib import ExitStack
import hashlib
import json
import socket
from types import SimpleNamespace

import pytest

from test_service_restart_contracts import RestartServer
from test_two_existing_mcp_clients import (
    ExistingClient,
    FASTMCP_DRIVER,
    INSPECTOR_DRIVER,
    _canonical,
    _dependencies,
)

from okto_nexus.adapters.outbound.cooperation_files import CooperationFiles
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_cooperation import TerminalCooperation


class InspectorPort:
    """Adapt the facade's existing Python port to the distributed JS client."""
    def __init__(self, client):
        self.client = client
        self.calls = []

    def discover(self):
        return self.client.request('discover')

    def call(self, tool, arguments, *, timeout=None):
        assert tool in {'message_create', 'handoff_create', 'coordination_request_get',
                        'message_status', 'handoff_get', 'event_cursor', 'event_wait'}
        assert timeout is None or 0 < timeout <= 35
        self.calls.append(tool)
        return self.client.request('call', tool, **arguments)


def effects(server):
    with server.deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        return dict(
            messages=[tuple(r) for r in conn.execute('SELECT message_id,from_agent_id,parent_message_id,workspace_id '
                'FROM messages ORDER BY message_id')],
            handoffs=[tuple(r) for r in conn.execute('SELECT handoff_id,status,claimed_by,claim_epoch,result '
                'FROM handoffs ORDER BY handoff_id')],
            requests=[tuple(r) for r in conn.execute('SELECT actor_agent_id,operation,client_request_id,resource_id '
                'FROM coordination_requests ORDER BY actor_agent_id,operation,client_request_id')],
            sessions=[tuple(r) for r in conn.execute('SELECT agent_id,session_id,workspace_id,status '
                'FROM sessions ORDER BY session_id')],
            authority=_canonical(server))


def test_existing_clients_complete_separately_consented_handoff_and_recover_same_ids(tmp_path):
    values, paths = _dependencies()
    with ExitStack() as cleanup:
        server = RestartServer(tmp_path)
        cleanup.callback(server.cleanup)
        keys = {}
        auth = AgentKeyAuthService(server.deps.repos.agents, server.deps.clock)
        with server.deps.connection_factory.unit_of_work() as uow:
            server.deps.repos.workspaces.upsert(uow, workspace_id='dx08-workspace', display_name='Synthetic DX08 workspace')
            for agent in ('dx08-inspector', 'dx08-fastmcp'):
                server.deps.repos.agents.upsert(uow, agent_id=agent, role='Synthetic cooperation participant')
                keys[agent] = auth.issue_key(uow, agent_id=agent)
        server.start()
        authority = _canonical(server)
        with server.deps.connection_factory.unit_of_work(write=False) as uow:
            server_id = uow.connection.execute('SELECT server_id FROM execution_installation').fetchone()[0]
        drivers = []
        clients = []
        for kind, body, executable, agent, extra in (
            ('inspector', INSPECTOR_DRIVER, [values['NEXUS_AC03_NODE']], 'dx08-inspector',
             {'inspector':values['NEXUS_AC03_INSPECTOR_ROOT']}),
            ('fastmcp', FASTMCP_DRIVER, [values['NEXUS_AC03_PYTHON'], '-I'], 'dx08-fastmcp',
             {'dependency_paths':paths}),
        ):
            path = tmp_path / (kind + ('.mjs' if kind == 'inspector' else '.py'))
            path.write_text(body,encoding='utf-8')
            drivers.append(path)
            client = ExistingClient(tmp_path, kind, [*executable,str(path)],
                dict(url=server.origin+'/mcp/',token=keys[agent],**extra),server.env)
            cleanup.callback(client.close)
            clients.append(client)
        inspector, peer = clients
        assert inspector.identity == dict(client='@modelcontextprotocol/inspector',version='0.21.2',sdk='1.29.0')
        assert peer.identity == dict(client='fastmcp',version='2.14.7',sdk='1.30.0')
        sid = inspector.request('call','session_open',agent_id='dx08-inspector',workspace_id='dx08-workspace')['session_id']
        peer.request('call','session_open',agent_id='dx08-fastmcp',workspace_id='dx08-workspace')
        scope = dict(origin=server.origin,server_id=server_id,agent_id='dx08-inspector',workspace_id='dx08-workspace')
        binding = document_revision({'fixture_profile':'dx08-existing-clients','scope':scope})
        store = CooperationFiles(tmp_path/'profile'/'cooperation',scope,binding)
        port = InspectorPort(inspector)
        requests = SimpleNamespace(load=store.load_request,save=store.save_request)
        flow = TerminalCooperation(port,scope,store.save,requests)
        before = effects(server)
        review = flow.review_exchange('dx08-fastmcp',binding,session_id=sid)
        assert review['consents'] == {'exchange':None,'handoff':None}
        assert effects(server) == before and port.calls == []
        for action in (lambda:flow.send_exchange('incorrect-review'),flow.review_handoff,
                       lambda:flow.send_handoff(review['review_revision'])):
            with pytest.raises(ConnectionError) as refused:
                action()
            assert refused.value.code == 'REVIEW_REQUIRED'
            assert effects(server) == before and port.calls == []
        sent = flow.send_exchange(review['review_revision'])
        assert sent['state'] == 'message_confirmed'
        message_id = sent['message_id']
        delivered = peer.request('call','inbox_pull',agent_id='dx08-fastmcp')['messages']
        assert [m['message_id'] for m in delivered] == [message_id]
        assert delivered[0]['from_agent_id'] == 'dx08-inspector'
        peer.request('call','inbox_ack',agent_id='dx08-fastmcp',message_ids=[message_id])
        reply = peer.request('call','message_create',from_agent_id='dx08-fastmcp',workspace_id='dx08-workspace',
            target={'strategy':'direct','agent_id':'dx08-inspector'},parent_message_id=message_id,
            body='DX08 synthetic correlated reply',client_request_id=sent['smoke_id']+':reply')
        current = flow.observe(timeout=0)
        assert current['state'] == 'exchange_proven' and current['historical'] is False
        assert current['evidence']['exchange']['reply_message_id'] == reply['message_id']
        assert current['checks']['handoff_test']['status'] == 'UNKNOWN'
        before_handoff = effects(server)
        handoff_review = flow.review_handoff()
        assert effects(server) == before_handoff
        assert handoff_review['reviews']['handoff'] != handoff_review['reviews']['exchange']
        assert handoff_review['consents']['handoff'] is None
        calls_before = list(port.calls)
        with pytest.raises(ConnectionError) as refused:
            flow.send_handoff(review['review_revision'])
        assert refused.value.code == 'REVIEW_REQUIRED'
        assert effects(server) == before_handoff and port.calls == calls_before
        created = flow.send_handoff(handoff_review['review_revision'])
        hid = created['handoff_id']
        claimed = peer.request('call','handoff_claim',workspace_id='dx08-workspace',
            handoff_id=hid,agent_id='dx08-fastmcp')
        epoch = claimed['claim_epoch']
        assert type(epoch) is int and epoch > 0 and claimed['claimed_by'] == 'dx08-fastmcp'
        result = {'outcome':'Synthetic DX08 canonical completion','smoke_id':sent['smoke_id']}
        peer.request('call','handoff_complete',workspace_id='dx08-workspace',handoff_id=hid,
            agent_id='dx08-fastmcp',claim_epoch=epoch,result=result)
        proven = flow.observe(timeout=0)
        assert proven['state'] == 'handoff_proven' and proven['historical'] is False
        assert all(check['status']=='PASS' for check in proven['checks'].values())
        assert proven['evidence']['handoff']['handoff_id'] == hid
        assert proven['evidence']['handoff']['claimed_by'] == 'dx08-fastmcp'
        assert proven['evidence']['handoff']['claim_epoch'] == epoch
        canonical = effects(server)
        assert canonical['authority'] == authority
        assert authority['runtime_sessions'] == authority['operations'] == 0
        assert len(canonical['handoffs']) == 1
        row, = canonical['handoffs']
        assert row[:4] == (hid,'COMPLETED','dx08-fastmcp',epoch)
        assert json.loads(row[4]) == result and result
        assert len(canonical['requests']) == 3  # exchange, reply, handoff
        resumed_store = CooperationFiles(store.directory,scope,binding)
        resumed = TerminalCooperation(port,scope,resumed_store.save,
            SimpleNamespace(load=resumed_store.load_request,save=resumed_store.save_request),resumed_store.load())
        assert resumed.status()['historical'] is True
        assert resumed.status()['smoke_id'] == sent['smoke_id']
        requests_before = dict(resumed.document['request_ids'])
        productive_before = [x for x in port.calls if x in ('message_create','handoff_create')]
        assert resumed.send_exchange(review['review_revision'])['message_id'] == message_id
        assert resumed.send_handoff(handoff_review['review_revision'])['handoff_id'] == hid
        recovered = resumed.observe(timeout=0)
        assert recovered['state'] == 'handoff_proven'
        assert recovered['request_ids'] == requests_before
        assert recovered['evidence']['handoff']['claim_epoch'] == epoch
        assert effects(server) == canonical
        assert [x for x in port.calls if x in ('message_create','handoff_create')] == productive_before
        checkpoints = b'\n'.join(p.read_bytes() for p in store.directory.rglob('*.json'))
        forbidden = [key.encode() for key in keys.values()] + [b'session_secret',b'DX08 synthetic correlated reply',
            b'Synthetic DX08 canonical completion']
        if any(value in checkpoints for value in forbidden):
            pytest.fail('Private material or payload was persisted in the facade checkpoint')
        proof = dict(clients=[c.identity for c in clients],smoke_id=sent['smoke_id'],
            message_id=message_id,reply_message_id=reply['message_id'],handoff_id=hid,claim_epoch=epoch,
            separate_consents=True,wrong_consent_refused=True,result_verified_in_canonical_table=True,
            resumed_same_ids=True,productive_calls=productive_before,identities_and_bindings_unchanged=True,
            runtime_operations=0,qualification='Distributed clients with real facade/TCP/SQLite; synthetic non-null result, no model.',
            drivers={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in drivers})
        (tmp_path/'public-cooperation-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
        for client in clients:
            client.close()
        server.stop()
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1',server.port)) != 0
