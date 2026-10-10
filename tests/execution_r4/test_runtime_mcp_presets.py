import pytest

from test_one_shot_capacity import conn
from okto_nexus.application import runtime_mcp_presets as presets
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def endpoints(conn):
    conn.execute("ALTER TABLE agent_endpoints ADD COLUMN protocol TEXT NOT NULL DEFAULT 'nxl-r4'")
    conn.execute("INSERT INTO agent_endpoints VALUES('runtime','nxl-r4'),('other','nxl-r4'),('mcp','mcp')")
    return conn


def test_revisioned_snapshot_is_not_mutated_by_later_save(endpoints):
    initial = presets.snapshot(endpoints, 'runtime')
    assert initial['revision'] == 0 and initial['servers'] == []
    old = presets.save(endpoints, endpoint_id='runtime', expected_revision=0,
        servers=[{'name': 'repo', 'transport': 'stdio', 'command': 'server'}])
    changed = presets.save(endpoints, endpoint_id='runtime', expected_revision=1,
        servers=[{'name': 'repo', 'transport': 'stdio', 'command': 'another-server'}])
    assert old['servers'][0]['command'] == 'server'
    assert old['configuration_digest'] != changed['configuration_digest']
    assert changed['revision'] == 2
    assert presets.snapshot(endpoints, 'other')['servers'] == []


def test_host_secret_reference_is_retained_without_resolution(endpoints):
    value = presets.save(endpoints, endpoint_id='runtime', expected_revision=0,
        servers=[{'name': 'repo', 'transport': 'http', 'url': 'https://example.test/mcp',
                  'header_refs': {'Authorization': 'vault:repo'}}])
    assert value['servers'][0]['header_refs'] == {'Authorization': 'vault:repo'}


def test_mcp_only_connection_rejects_preset(endpoints):
    with pytest.raises(OktoNexusError):
        presets.save(endpoints, endpoint_id='mcp', expected_revision=0, servers=[])


def test_stale_revision_does_not_overwrite(endpoints):
    presets.save(endpoints, endpoint_id='runtime', expected_revision=0,
        servers=[{'name': 'repo', 'transport': 'stdio', 'command': 'server'}])
    with pytest.raises(OktoNexusError):
        presets.save(endpoints, endpoint_id='runtime', expected_revision=0, servers=[])
    assert presets.snapshot(endpoints, 'runtime')['servers']


def test_digest_detects_corruption(endpoints):
    presets.save(endpoints, endpoint_id='runtime', expected_revision=0,
        servers=[{'name': 'repo', 'transport': 'stdio', 'command': 'server'}])
    endpoints.execute("UPDATE runtime_mcp_presets SET preset_json='[]' WHERE endpoint_id='runtime'")
    with pytest.raises(OktoNexusError):
        presets.snapshot(endpoints, 'runtime')
