"""Isolated browser proof of the operator connection setup and copied request."""
import json
import os

import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_runtime_input_dashboard import dashboard as dashboard_fixture
from test_runtime_input_dashboard import dashboard_build as build_fixture

runtime = runtime_fixture
dashboard = dashboard_fixture
dashboard_build = build_fixture
pytestmark = pytest.mark.skipif(os.environ.get('OKTO_NEXUS_UI_CAMPAIGN') != '1', reason='Isolated browser campaign not enabled')


def test_agent_connection_policy_issue_copy_and_revoke(runtime, dashboard):
    from playwright.sync_api import expect

    page = dashboard
    page.get_by_role('button', name='Agents', exact=True).click()
    panel = page.get_by_test_id('agent-connections-worker')
    page.get_by_test_id('connections-worker').click()
    expect(panel.get_by_label('Pi · RPC', exact=True)).to_be_checked()
    panel.get_by_label('Connection key expiration', exact=True).select_option('unlimited')
    panel.get_by_role('button', name='Save connection policy').click()
    expect(panel.get_by_role('status')).to_have_text('Connection policy saved.')
    panel.get_by_test_id('connection-endpoint-endpoint-pi').get_by_role('button', name='Issue key and prepare request').click()
    field = panel.get_by_label('Connection request', exact=True)
    expect(field).to_be_visible()
    request = json.loads(field.input_value())
    assert request['body'] == {}
    assert request['headers']['Authorization'].startswith('Bearer nxsconn_')
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    panel.get_by_role('button', name='Copy request', exact=True).click()
    expect(panel.get_by_role('status')).to_have_text('Request copied.')
    assert json.loads(page.evaluate('navigator.clipboard.readText()')) == request
    response = runtime[1].post(request['url'], headers=request['headers'], json=request['body'])
    assert response.status_code == 200, response.text
    panel.get_by_role('button', name='Revoke', exact=True).click()
    expect(field).to_have_count(0)
    assert runtime[1].post(request['url'], headers=request['headers'], json={}).status_code == 403
    page.screenshot(path=str(__import__('pathlib').Path(runtime[2]).parent / 'agent-connections.png'), full_page=True)
