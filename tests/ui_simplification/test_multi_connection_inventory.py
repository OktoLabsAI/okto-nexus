"""Whole HTTP inventory keeps sibling connections and productive work distinct."""
from fastapi.testclient import TestClient

from .test_entry_pages import scenario  # noqa: F401
from .test_fixtures import fixtures


def test_all_scope_paginates_same_agent_connections_without_work_duplication(request):
    s = request.getfixturevalue('scenario')
    client = TestClient(s.app, headers={
        'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator'],
    })

    def read(**params):
        response = client.get('/api/v1/home/entries', params={
            'quick': 'all', 'limit': 1, **params,
        })
        assert response.status_code == 200, response.text
        value = response.json()['data']
        assert value['status'] == 'ready' and value['total_is_exact']
        return value

    try:
        groups, cursor = [], None
        while True:
            page = read(**({'cursor': cursor} if cursor else {}))
            groups.extend(page['items'])
            cursor = page['next_cursor']
            if cursor is None:
                break
        assert len(groups) == len({g['id'] for g in groups}) == page['total']
        siblings = {g['connection']['binding_id']: g for g in groups
                    if g['connection'] and g['connection']['agent_id'] == 'subject'}
        assert {'binding', 'ui-binding-2'} <= siblings.keys()
        assert siblings['binding']['id'] != siblings['ui-binding-2']['id']
        children, parent_by_child = [], {}
        for group in groups:
            rows, child_cursor = list(group['children']), group['children_cursor']
            while child_cursor:
                child_page = read(partition='children', group_id=group['id'], cursor=child_cursor)
                rows.extend(child_page['items'])
                child_cursor = child_page['next_cursor']
            assert len(rows) == group['children_total']
            parent_by_child.update({row['id']: group['id'] for row in rows})
            children.extend(rows)
        assert len(children) == len({row['id'] for row in children})
        blocked = next(row for row in children if any(
            ref['session_id'] == s.sessions[0] for ref in row['sessions']))
        completed = next(row for row in children if row['source_ref']['id'] == 'ui-success')
        assert parent_by_child[blocked['id']] == siblings['binding']['id']
        assert blocked['attention_refs'] and blocked['display_state'] == 'awaiting_operator'
        assert parent_by_child[completed['id']] == siblings['ui-binding-2']['id']
        assert completed['results_preview'] and completed['display_state'] != 'awaiting_operator'
        productive = [row for row in children if row['kind'] == 'work']
        assert page['summary']['activities']['value'] == len(productive)
        assert page['inventory']['connections']['value'] == 2
        with s.factory.unit_of_work(write=False) as uow:
            connection_agents = uow.connection.execute(
                'SELECT e.agent_id FROM execution_bindings b JOIN agent_endpoints e USING(endpoint_id)'
            ).fetchall()
            assert [row[0] for row in connection_agents] == ['subject', 'subject']
        with s.factory.unit_of_work() as uow:
            s.deps.repos.workspaces.upsert(uow, workspace_id='inventory-second-project')
            original = uow.connection.execute(
                "SELECT * FROM handoffs WHERE handoff_id='ui-unassigned'"
            ).fetchone()
            fixtures._copy(uow.connection, 'handoffs', original,
                           handoff_id='inventory-second-project-work',
                           workspace_id='inventory-second-project')
        union = read(limit=100)
        assert union['summary']['activities']['value'] == len(productive) + 1
        assert union['inventory']['connections']['value'] == 2
        assert len([row for group in union['items'] for row in group['children']
                    if row['source_ref']['id'] == 'inventory-second-project-work']) == 1
        scoped = read(workspace_id='ws', limit=100)
        assert scoped['summary']['activities']['value'] == len(productive)
        assert all(group['workspace_id'] == 'ws' for group in scoped['items'])
    finally:
        client.close()
