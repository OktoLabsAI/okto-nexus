"""Session read tools: inbox_count, inbox_peek, inbox_history and message_status (#91)."""
import pytest

from test_mcp_session_capabilities import opening, activate, rpc, envelope
from okto_nexus.application import execution_tools
from okto_nexus.bootstrap.embedded_tools import MCP_ACTIONS

TOOLS = ('inbox_count', 'inbox_peek', 'inbox_history', 'message_status')
NOT_FOUND_TEXT = 'No such message. Pass the message_id returned by message_create.'


def call_args(name, **extra):
    base = {'message_status': {'message_id': 'sent'}}.get(name, {'agent_id': 'subject'})
    return base | extra


def seed_messages(state):
    deps = state[0]
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        for message_id, sender in (('sent', 'subject'), ('foreign', 'other')):
            uow.connection.execute(
                'INSERT INTO messages(message_id,workspace_id,from_agent_id,subject,body,created_at) '
                'VALUES(?,?,?,?,?,?)', (message_id, 'ws', sender, 'S', 'B', now))


def test_tool_sets_name_the_four_read_tools_and_keep_mutations_denied():
    assert set(TOOLS) <= execution_tools.MANAGED_TOOLS and set(TOOLS) <= set(MCP_ACTIONS)
    for name in ('inbox_pull', 'inbox_ack', 'inbox_extend'):
        assert name not in execution_tools.MANAGED_TOOLS and name not in MCP_ACTIONS


@pytest.mark.parametrize('name', TOOLS)
def test_each_read_tool_passes_with_the_right_capability(opening, name):
    seed_messages(opening)
    cap = activate(opening, actions=['tools/call', name])
    result = envelope(rpc(opening, cap['capability'], name, call_args(name)))
    assert result['ok'], result


@pytest.mark.parametrize('name', TOOLS)
def test_each_read_tool_is_denied_with_the_protocol_ceiling_only(opening, name):
    seed_messages(opening)
    cap = activate(opening, actions=['tools/call'])
    result = envelope(rpc(opening, cap['capability'], name, call_args(name)))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


@pytest.mark.parametrize('name', ('inbox_count', 'inbox_peek', 'inbox_history'))
def test_another_agent_inbox_is_denied(opening, name):
    cap = activate(opening, actions=['tools/call', name])
    result = envelope(rpc(opening, cap['capability'], name, {'agent_id': 'other'}))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


@pytest.mark.parametrize('name', ('inbox_pull', 'inbox_ack', 'inbox_extend'))
def test_pull_ack_and_extend_stay_denied(opening, name):
    cap = activate(opening, actions=['tools/call', name])
    result = envelope(rpc(opening, cap['capability'], name, {'agent_id': 'subject', 'message_ids': ['sent'], 'extend_seconds': 30}))
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result


def test_message_status_is_sender_only_with_the_missing_id_text(opening):
    seed_messages(opening)
    cap = activate(opening, actions=['tools/call', 'message_status'])
    own = envelope(rpc(opening, cap['capability'], 'message_status', {'message_id': 'sent'}))
    assert own['ok'] and own['data']['message_id'] == 'sent', own
    foreign = envelope(rpc(opening, cap['capability'], 'message_status', {'message_id': 'foreign'}))
    missing = envelope(rpc(opening, cap['capability'], 'message_status', {'message_id': 'nothing'}))
    for result in (foreign, missing):
        assert not result['ok'] and result['error']['code'] == 'NOT_FOUND', result
        assert result['error']['message'] == NOT_FOUND_TEXT


def test_key_caller_service_keeps_the_old_shape():
    from okto_nexus.application.inbox import InboxService
    import inspect
    assert inspect.signature(InboxService.message_status).parameters['caller_agent_id'].default is None


def test_capability_issued_before_the_change_is_denied_and_reissued_passes(opening, monkeypatch):
    seed_messages(opening)
    old_actions = [a for a in MCP_ACTIONS if a not in TOOLS]
    old = activate(opening, actions=old_actions)
    denied = envelope(rpc(opening, old['capability'], 'inbox_count', {'agent_id': 'subject'}))
    assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
    from test_session_capabilities import issue
    reissued = issue(opening, request_id='cap-request-2', actions=list(MCP_ACTIONS))
    assert reissued.status_code == 200, reissued.text
    result = envelope(rpc(opening, reissued.json()['capability'], 'inbox_count', {'agent_id': 'subject'}))
    assert result['ok'], result


def test_publication_status_reports_relay_state():
    import sqlite3
    from okto_nexus.application.inbox import InboxService
    from types import SimpleNamespace
    from contextlib import contextmanager
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE runtime_results(publication_message_id TEXT, relay_state TEXT, captured_at TEXT)')
    db.execute("INSERT INTO runtime_results VALUES('pub','BLOCKED','2026-10-25')")
    uow = SimpleNamespace(connection=db)
    class Factory:
        @contextmanager
        def unit_of_work(self, write=True):
            yield uow
    messages = SimpleNamespace(list_by_ids=lambda u, message_ids: [SimpleNamespace(from_agent_id='subject')])
    deliveries = SimpleNamespace(list_for_message=lambda u, message_id, now: [])
    service = InboxService.__new__(InboxService)
    service._cf, service._messages, service._deliveries = Factory(), messages, deliveries
    service._clock = SimpleNamespace(now_iso=lambda: '2026-10-25')
    assert service.message_status(message_id='pub', caller_agent_id='subject')['relay_state'] == 'BLOCKED'
    assert 'relay_state' not in service.message_status(message_id='plain', caller_agent_id='subject')
