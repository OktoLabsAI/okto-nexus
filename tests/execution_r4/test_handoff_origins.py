"""Creator provenance is authenticated before persistence, including approval."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_mcp_session_capabilities import opening, activate, rpc, envelope
from okto_nexus.application.message_session_origin import runtime_key
from okto_nexus.adapters.outbound.sqlite.handoff_origins import SqliteHandoffOriginRepo


def arguments(**updates):
    return dict(workspace_id='ws', from_agent_id='subject', target={'strategy': 'broadcast'},
                visibility='eligible', payload='Review this work') | updates


def create(state, secret=None, **updates):
    return envelope(rpc(state, secret or state[1].state.test_agent_keys['subject'],
                        'handoff_create', arguments(**updates)))


def origin(state, result):
    assert result['ok'], result
    with state[0].connection_factory.unit_of_work(write=False) as uow:
        return SqliteHandoffOriginRepo().get(uow, workspace_id='ws', handoff_id=result['data']['handoff_id'])


def session(state, actor='subject'):
    response = envelope(rpc(state, state[1].state.test_agent_keys[actor], 'session_open',
                            {'agent_id': actor, 'workspace_id': 'ws'}))
    assert response['ok'], response
    return response['data']


@pytest.mark.parametrize('opening', ['strict'], indirect=True)
def test_managed_mcp_creator_uses_its_runtime_origin_and_no_legacy_secret(opening):
    cap = activate(opening, actions=['tools/call', 'handoff_create'])
    created = create(opening, cap['capability'])
    provenance = origin(opening, created)
    assert provenance.source_session_key == runtime_key(cap['scope']) and provenance.kind == 'runtime'
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        stored = dict(uow.connection.execute('SELECT * FROM execution_handoff_origins').fetchone())
        assert cap['capability'] not in str(stored) and 'secret' not in str(stored)


@pytest.mark.parametrize('changes', [{'session_id': 'foreign'}, {'session_secret': 'fake'},
    {'workspace_id': 'elsewhere'}, {'from_agent_id': 'other'}])
def test_managed_creator_cannot_supply_another_origin(opening, changes):
    cap = activate(opening, actions=['tools/call', 'handoff_create'])
    result = create(opening, cap['capability'], **changes)
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM handoffs').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_handoff_origins').fetchone()[0] == 0


def test_tool_ceiling_is_required(opening):
    cap = activate(opening, actions=['tools/call'])
    result = create(opening, cap['capability'])
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED'


@pytest.mark.parametrize('opening', [{'subject_permissions': {'handoffs': {'create': False}}}], indirect=True)
def test_agent_permission_is_required_even_with_capability_action(opening):
    cap = activate(opening, actions=['tools/call', 'handoff_create'])
    result = create(opening, cap['capability'])
    assert not result['ok'] and result['error']['code'] == 'PERMISSION_DENIED', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('proved', [False, True])
def test_mcp_session_id_alone_never_selects_a_privileged_affinity(opening, proved):
    legacy = session(opening)
    created = create(opening, session_id=legacy['session_id'],
                     **({'session_secret': legacy['session_secret']} if proved else {}))
    value = origin(opening, created)
    assert value.kind == ('mcp' if proved else 'missing')
    assert value.source_session_key == (json.dumps(['mcp', legacy['session_id']], separators=(',', ':')) if proved else '')


@pytest.mark.parametrize('wrong_owner', [False, True])
def test_wrong_session_proof_leaves_no_handoff_or_origin(opening, wrong_owner):
    legacy = session(opening, actor='other' if wrong_owner else 'subject')
    result = create(opening, session_id=legacy['session_id'],
                    session_secret=legacy['session_secret'] if wrong_owner else 'wrong')
    assert not result['ok'] and result['error']['code'] == 'NOT_OWNER', result
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM handoffs').fetchone()[0] == 0


def approval(state, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_hitl import _attach, _rule
    state[0].config.feature_hitl = True
    _attach(state[0], 'subject', governance=[_rule('handoff_create', 'require_approval')])


def approve(state, approval_id):
    return TestClient(state[1], base_url='https://127.0.0.1:8202').post(
        f'/api/v1/approvals/{approval_id}/decision', json={'decision': 'approve'},
        headers={'Authorization': 'Bearer ' + state[1].state.test_agent_keys['operator']})


def test_approval_keeps_verified_mcp_origin_after_legacy_session_closes(opening, monkeypatch):
    approval(opening, monkeypatch)
    legacy = session(opening)
    pending = create(opening, session_id=legacy['session_id'], session_secret=legacy['session_secret'])
    assert pending['ok'] and pending['data']['status'] == 'pending_approval', pending
    aid = pending['data']['approval_id']
    kwargs = opening[0].approvals.get_approval(approval_id=aid)['request_payload']['kwargs']
    assert legacy['session_secret'] not in str(kwargs) and 'session_secret' not in kwargs and 'session_id' not in kwargs
    expected = json.dumps(['mcp', legacy['session_id']], separators=(',', ':'))
    assert kwargs['_source_session_key'] == expected
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE sessions SET status='closed' WHERE session_id=?", (legacy['session_id'],))
    response = approve(opening, aid)
    assert response.status_code == 200, response.text
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT source_session_key FROM execution_handoff_origins').fetchone()[0] == expected


@pytest.mark.parametrize('revoke', [False, True])
def test_managed_creator_approval_preserves_origin_and_rechecks_authority(opening, monkeypatch, revoke):
    approval(opening, monkeypatch)
    cap = activate(opening, actions=['tools/call', 'handoff_create'])
    pending = create(opening, cap['capability'])
    assert pending['ok'] and pending['data']['status'] == 'pending_approval', pending
    aid = pending['data']['approval_id']
    recorded = opening[0].approvals.get_approval(approval_id=aid)['request_payload']['kwargs']
    assert recorded['_source_session_key'] == runtime_key(cap['scope'])
    assert cap['capability'] not in str(recorded)
    if revoke:
        with opening[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?', (opening[0].clock.now_iso(),))
    response = approve(opening, aid)
    assert response.status_code == (403 if revoke else 200), response.text
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT source_session_key FROM execution_handoff_origins').fetchall()
        assert len(rows) == (0 if revoke else 1)
        if not revoke:
            assert rows[0][0] == runtime_key(cap['scope'])


def test_origin_and_handoff_share_transaction_and_history_has_explicit_fallback(opening):
    from test_mcp_session_capabilities import seed_work
    seed_work(opening)
    with opening[0].connection_factory.unit_of_work() as uow:
        assert SqliteHandoffOriginRepo().get(uow, workspace_id='ws', handoff_id='work').kind == 'missing'
        uow.connection.execute("CREATE TRIGGER origin_failure BEFORE INSERT ON execution_handoff_origins "
                               "BEGIN SELECT RAISE(ABORT,'injected origin storage failure'); END")
    result = create(opening)
    assert not result['ok']
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM handoffs').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_handoff_origins').fetchone()[0] == 0
