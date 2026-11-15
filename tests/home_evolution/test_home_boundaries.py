"""Home result boundaries over real SQLite and ASGI, without native execution.

Synthetic handoff facts are explicitly fixtures. Artifacts use the actual
managed store and HTTP route; no browser, sockets, provider or personal data.
"""
# ruff: noqa: F811 -- imported pytest fixtures are resolved by their names
import json

import pytest

from okto_nexus.adapters.inbound.mcp.tools.artifacts import build_service
from .fixtures import OPERATOR, WORKSPACES, home_scenario as home_scenario
from .test_home_queries import service as service
from .test_home_http import http as http


CANONICAL_TABLES = (
    'handoffs', 'messages', 'message_deliveries', 'execution_operations',
    'execution_receipts', 'execution_results', 'runtime_execution_grants',
)


def canonical_rows(scenario):
    with scenario.factory.unit_of_work(write=False) as uow:
        return {name: sorted([tuple(r) for r in uow.connection.execute('SELECT * FROM ' + name)], key=repr)
                for name in CANONICAL_TABLES}


def completed_handoffs(scenario):
    with scenario.factory.unit_of_work() as uow:
        for ident in ('fixture-handoff-0000', 'fixture-handoff-0002', 'fixture-handoff-0001'):
            uow.connection.execute("UPDATE handoffs SET status='COMPLETED',result=?,claim_epoch=1 WHERE handoff_id=?",
                                   ('Synthetic durable result ' + ident, ident))


def result_map(service, workspace):
    return {item['source_ref']['id']: item for item in service.read(
        context=OPERATOR, section='results', filters={'workspace_id': workspace})['items']}


def test_home_reads_and_exact_seen_preserve_unread_other_page_other_workspace_and_canonical_facts(service, home_scenario):
    completed_handoffs(home_scenario)
    baseline = canonical_rows(home_scenario)
    first = service.read(context=OPERATOR, section='results', filters={'workspace_id': WORKSPACES[0]}, limit=1)
    assert first['has_more'] and first['next_cursor']
    selected = first['items'][0]
    # Select a real result occurrence rather than using agent/global timestamps.
    assert selected['attention'] and selected['view_state'] == 'unseen'
    before_a = result_map(service, WORKSPACES[0])
    before_b = result_map(service, WORKSPACES[1])
    service.read(context=OPERATOR, filters={'workspace_id': WORKSPACES[0]})
    service.resolve(context=OPERATOR, target=selected['detail_target'], workspace_id=WORKSPACES[0])
    assert canonical_rows(home_scenario) == baseline
    assert result_map(service, WORKSPACES[0]) == before_a
    assert result_map(service, WORKSPACES[1]) == before_b
    occurrence = selected['attention']
    service.attention.mark_seen(context=OPERATOR, attention_id=occurrence['attention_id'],
        source_revision=occurrence['source_revision'], preference_revision=occurrence['seen_state']['revision'])
    after_a = result_map(service, WORKSPACES[0])
    assert after_a[selected['source_ref']['id']]['view_state'] == 'seen'
    for ident, old in before_a.items():
        if ident != selected['source_ref']['id']:
            assert after_a[ident]['view_state'] == old['view_state']
            assert after_a[ident]['attention'] == old['attention']
    assert result_map(service, WORKSPACES[1]) == before_b
    assert canonical_rows(home_scenario) == baseline


@pytest.fixture
def stored_html(http, tmp_path):
    project = tmp_path / 'artifact-project'
    project.mkdir()
    with http.deps.connection_factory.unit_of_work() as uow:
        http.deps.repos.agents.upsert(uow, agent_id='artifact-author', role='agent')
        key = http.app.state.auth.issue_key(uow, agent_id='artifact-author')
        http.deps.repos.workspaces.upsert(uow, workspace_id='other-workspace')
    payload = '<!doctype html><script>window.fixturePrivilegeMarker=true</script><p>Fixture</p>'
    artifact = build_service(http.deps).artifact_put(project_root=str(project), artifact_type='html',
        name='Untrusted fixture', content=payload, agent_id='artifact-author')
    return artifact, payload, key


def test_artifact_reference_never_grants_agent_read_or_cross_workspace_access(http, stored_html):
    artifact, payload, key = stored_html
    route = '/api/v1/artifacts/' + artifact['artifact_id']
    for suffix in ('', '/content'):
        denied = http.client.get(route + suffix, headers={'X-API-Key': key}, params={'workspace': 'all'})
        assert denied.status_code == 403
        assert payload not in denied.text
        wrong = http.client.get(route + suffix, params={'workspace': 'other-workspace'})
        assert wrong.status_code == 404
        assert payload not in wrong.text
    allowed = http.client.get(route, params={'workspace': 'all'})
    assert allowed.status_code == 200
    assert allowed.json()['data']['artifact_id'] == artifact['artifact_id']


@pytest.mark.parametrize('filename,media_type,payload', [
    ('untrusted.html', 'text/html', '<!doctype html><script>window.fixturePrivilegeMarker=true</script>'),
    ('untrusted.svg', 'image/svg+xml', '<svg xmlns="http://www.w3.org/2000/svg"><script>window.fixturePrivilegeMarker=true</script></svg>'),
    ('untrusted.xhtml', 'application/xhtml+xml', '<html xmlns="http://www.w3.org/1999/xhtml"><script>window.fixturePrivilegeMarker=true</script></html>'),
])
def test_html_artifact_cannot_execute_with_operator_origin_privileges(http, stored_html, filename, media_type, payload):
    existing, _, _ = stored_html
    artifact = build_service(http.deps).artifact_upload(workspace_id=existing['workspace_id'],
        filename=filename, media_type=media_type, data=payload.encode(), agent_id='artifact-author')
    response = http.client.get('/api/v1/artifacts/' + artifact['artifact_id'] + '/content', params={'workspace': 'all'})
    assert response.status_code == 200
    assert response.text == payload
    disposition = response.headers.get('content-disposition', '').lower()
    policy = response.headers.get('content-security-policy', '').lower()
    # Inline active HTML must have an opaque sandbox origin; attachment delivery
    # also prevents executing the response as the dashboard document.
    assert disposition.startswith('attachment') or (
        'sandbox' in policy and 'allow-same-origin' not in policy
    ), json.dumps({'content_type': response.headers.get('content-type'),
                   'disposition': disposition, 'csp': policy})
    assert response.headers.get('x-content-type-options') == 'nosniff'
