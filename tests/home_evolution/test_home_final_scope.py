"""Adversarial scoped reads against migrated SQLite and real ASGI routes.

No network listener, runtime host or provider is used. Technical states are
synthetic canonical rows, not claims of actual native execution.
"""
# ruff: noqa: F811 -- pytest fixtures imported explicitly
import json

import pytest

from .fixtures import home_scenario as home_scenario, OPERATOR, WORKSPACES
from .test_home_queries import service as service, link_handoff
from .test_home_http import http as http


def copy_row(conn, table, row, **changes):
    value = dict(row, **changes)
    conn.execute('INSERT INTO '+table+'('+','.join(value)+') VALUES('
                 +','.join('?' for _ in value)+')', tuple(value.values()))


def read_http(http, service, section='overview', **params):
    # Keep real HTTP middleware/router and inject the same migrated synthetic
    # service used by the SQL assertions; no credential or auth override.
    http.app.state.home = service
    response = http.client.get('/api/v1/home/'+section, params=params)
    assert response.status_code == 200, response.text
    return response.json()['data']


def all_pages(http, service, section, workspace=None):
    params = {'limit': 2}
    if workspace:
        params['workspace_id'] = workspace
    rows = []
    for _ in range(20):
        page = read_http(http, service, section, **params)
        rows.extend(page['items'])
        assert page['total_is_exact']
        if not page['has_more']:
            assert len(rows) == page['total']
            return rows
        assert page['next_cursor']
        params['cursor'] = page['next_cursor']
    pytest.fail('pagination did not terminate')


def test_project_a_unchanged_when_same_agent_adds_b_work_attention_and_results(http, service, home_scenario):
    a, b = WORKSPACES
    before_a = read_http(http, service, workspace_id=a)
    before_b = read_http(http, service, workspace_id=b)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        assert c.execute("SELECT COUNT(DISTINCT workspace_id) FROM sessions WHERE agent_id='A'").fetchone()[0] == 2
        row = c.execute("SELECT * FROM handoffs WHERE workspace_id=? LIMIT 1", (b,)).fetchone()
        copy_row(c, 'handoffs', row, handoff_id='beta-result', from_agent_id='A',
                 status='COMPLETED', result='Only project B result', claim_epoch=1)
        copy_row(c, 'handoffs', row, handoff_id='beta-verifying', from_agent_id='A',
                 status='VERIFYING', claimed_by='B', claim_epoch=1,
                 verify_by=json.dumps({'kind':'agent','agent_id':'operator'}))
        c.execute("INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,created_at) VALUES(?,'message','message.created','A',?,'public',?)",
                  (b, json.dumps({'message_id':'beta-event'}), home_scenario.clock.now_iso()))
    after_a = read_http(http, service, workspace_id=a)
    after_b = read_http(http, service, workspace_id=b)
    for section in ('work', 'results', 'attention', 'agents', 'external_activity'):
        assert after_a[section] == before_a[section], section
    assert after_a['summary'] == before_a['summary']
    assert all_pages(http, service, 'activity', a) == []
    assert any(row['kind']=='message.created' for row in all_pages(http, service, 'activity', b))
    assert after_b['results']['total'] == before_b['results']['total'] + 1
    assert after_b['summary']['needs_you']['value'] > before_b['summary']['needs_you']['value']
    assert any(row['source_ref']['id']=='beta-verifying' for row in after_b['work']['items'])


def test_all_projects_is_exact_paged_union_despite_repeated_memberships_and_links(http, service, home_scenario):
    link_handoff(home_scenario)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        for agent in ('A','B','C','global','revoked'):
            for workspace in WORKSPACES:
                for n in range(3):
                    home_scenario.repos.sessions.create(uow, session_id=f'repeated-{agent}-{workspace}-{n}',
                        agent_id=agent, workspace_id=workspace, status='active')
        original = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone()
        for n in range(3):
            operation = f'linked-retry-{n}'
            copy_row(c, 'execution_operations', original, operation_id=operation)
            c.execute('INSERT INTO execution_domain_deliveries VALUES(?,?,?,?)',
                      ('fixture-server','fixture-executor',operation,'domain-work'))
        c.execute("UPDATE handoffs SET status='COMPLETED',result='Beta result',claim_epoch=1 WHERE handoff_id='fixture-handoff-0001'")
    for section, identity in (('work','id'),('results','id'),('agents','agent_id')):
        scoped = [all_pages(http, service, section, workspace) for workspace in WORKSPACES]
        union = {row[identity] for page in scoped for row in page}
        combined = all_pages(http, service, section)
        assert {row[identity] for row in combined} == union
        assert len(combined) == len(union), section
    combined = all_pages(http, service, 'work')
    linked = [row for row in combined if row['source_ref']['id']=='fixture-handoff-0000']
    assert len(linked) == 1
    assert linked[0]['attempt_count'] == 4
    assert not any(row['source_ref']['id']=='domain-work' for row in combined)


@pytest.mark.parametrize('lifecycle,containment', [('READY',False),('OPENING',False),('READY',True)])
def test_technical_open_or_cleanup_without_turn_is_not_productive_work(service, home_scenario, lifecycle, containment):
    before = service.read(context=OPERATOR)
    with home_scenario.factory.unit_of_work() as uow:
        c = uow.connection
        opening = c.execute("SELECT * FROM execution_operations WHERE action='runtime.open'").fetchone()
        session = c.execute('SELECT * FROM execution_sessions').fetchone()
        copy_row(c, 'execution_operations', opening, operation_id='technical-open', session_id='technical-session',
                 admission_state='ACCEPTED')
        copy_row(c, 'execution_sessions', session, session_id='technical-session', open_operation_id='technical-open',
                 lifecycle_state=lifecycle)
        c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES('fixture-server','fixture-executor','technical-open',1,?,'SUBMITTED',1,0,?)",
                  (opening['intent_hash'],home_scenario.clock.now_iso()))
        if containment:
            old = c.execute('SELECT * FROM execution_session_containment').fetchone()
            copy_row(c, 'execution_session_containment', old, session_id='technical-session', opening_operation_id='technical-open')
        assert c.execute("SELECT COUNT(*) FROM execution_operations WHERE session_id='technical-session' AND action='turn.submit'").fetchone()[0] == 0
    after = service.read(context=OPERATOR)
    assert after['work'] == before['work']
    assert after['results'] == before['results']
    for counter in ('running','waiting_start'):
        assert after['summary'][counter] == before['summary'][counter]
