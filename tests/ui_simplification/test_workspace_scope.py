"""Global identities cannot carry another workspace's work into a Home page."""
from fastapi.testclient import TestClient

from .test_entry_pages import scenario as scenario
from .test_fixtures import fixtures


def test_http_workspace_filters_precede_counts_inventory_and_pagination(request):
    s = request.getfixturevalue('scenario')
    client = TestClient(s.app, headers={'Authorization': 'Bearer ' + s.app.state.test_agent_keys['operator']})

    def read(workspace, **extra):
        response = client.get('/api/v1/home/entries', params=dict(workspace_id=workspace, quick='all', limit=1, **extra))
        assert response.status_code == 200, response.text
        return response.json()['data']

    def collect(workspace):
        groups, cursor = [], None
        while True:
            value = read(workspace, **({'cursor': cursor} if cursor else {}))
            groups.extend(value['items'])
            cursor = value['next_cursor']
            if cursor is None:
                return groups, value

    try:
        before, before_page = collect('ws')
        with s.factory.unit_of_work() as uow:
            s.deps.repos.workspaces.upsert(uow, workspace_id='ui-scope-other')
            original = uow.connection.execute("SELECT * FROM handoffs WHERE handoff_id='ui-unassigned'").fetchone()
            # Same global sender acts in two authorized projects. This is an
            # owned historical read fact, not a new runtime/grant authorization.
            fixtures._copy(uow.connection, 'handoffs', original,
                           handoff_id='ui-other-project-work', workspace_id='ui-scope-other')
        after, after_page = collect('ws')
        assert after == before
        for key in ('total', 'summary', 'inventory'):
            assert after_page[key] == before_page[key]
        assert all(group['workspace_id'] == 'ws' for group in after)
        other, other_page = collect('ui-scope-other')
        assert other_page['total'] == len(other) == 1
        assert other[0]['children'][0]['source_ref']['id'] == 'ui-other-project-work'
        assert other_page['inventory']['connections']['value'] == 0
        # Operator is a global identity with work elsewhere, not a participant
        # of this new project merely because it may inspect the project.
        unrelated = read('ui-scope-other', agent_id='operator')
        assert unrelated['items'] == [] and unrelated['total'] == 0
    finally:
        client.close()
