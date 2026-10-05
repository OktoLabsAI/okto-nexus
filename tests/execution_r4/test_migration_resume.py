"""Resume a migration after reviewed adoption without losing source history."""
import pytest

from okto_nexus.bootstrap.execution_migration import migrate_execution_catalog
from test_binding_migration import adopted_setup, proposal_request
from test_binding_operator import prepare_operator


@pytest.mark.parametrize("change, message", [
    ("endpoint", "adopted migration resource changed"),
    ("profile", "adopted migration resource changed"),
    ("binding", "adopted migration resource changed"),
    ("legacy_profile", "preserved migration source row"),
    ("credential", "preserved migration source row"),
    ("receipt", "no verifiable migration receipt"),
    ("partial_receipt", "no verifiable migration receipt"),
    ("owner", "Stop and drain"),
])
def test_migration_resumes_after_adoption_and_rejects_later_drift(tmp_path, monkeypatch, request, change, message):
    fixture = adopted_setup.__wrapped__(tmp_path,monkeypatch,request)
    setup = next(fixture)
    deps,_,client,headers,*_=setup
    try:
        _,apply = prepare_operator(client,headers,proposal_request(setup))
        response = client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"])
        assert response.status_code == 200,response.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            maps = [dict(row) for row in uow.connection.execute("SELECT * FROM execution_migration_map ORDER BY source_type,legacy_id")]
            policies = [tuple(row) for row in uow.connection.execute("SELECT enabled,activation_state FROM agent_endpoints")]
            legacy_profile = dict(uow.connection.execute("SELECT * FROM runtime_profiles WHERE profile_id='legacy-profile'").fetchone())
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    for _ in range(2):
        report=migrate_execution_catalog(deps.config.db_path,tmp_path/"migration-backup",batch_size=1)
        assert report["status"]=="CATALOG_BACKFILL_COMPLETE" and report["processed"]==0
    with deps.connection_factory.unit_of_work() as uow:
        assert [dict(row) for row in uow.connection.execute("SELECT * FROM execution_migration_map ORDER BY source_type,legacy_id")] == maps
        assert [tuple(row) for row in uow.connection.execute("SELECT enabled,activation_state FROM agent_endpoints")] == policies
        assert dict(uow.connection.execute("SELECT * FROM runtime_profiles WHERE profile_id='legacy-profile'").fetchone()) == legacy_profile
        mutations = {
            "endpoint": "UPDATE agent_endpoints SET enabled=1 WHERE endpoint_id='legacy-endpoint'",
            "profile": "UPDATE runtime_profiles SET enabled=0 WHERE profile_id<>'legacy-profile'",
            "binding": "UPDATE execution_bindings SET binding_revision=binding_revision+1",
            "legacy_profile": "UPDATE runtime_profiles SET config='{}' WHERE profile_id='legacy-profile'",
            "credential": "UPDATE agents SET api_key_hash='changed' WHERE agent_id='subject'",
            "receipt": "UPDATE execution_migration_map SET canonical_ref=json_remove(canonical_ref,'$.adoption') WHERE state='BINDING_ADOPTED'",
            "partial_receipt": "UPDATE execution_migration_map SET canonical_ref=json_remove(canonical_ref,'$.adoption.binding_digest') WHERE state='BINDING_ADOPTED'",
            "owner": "UPDATE runtime_dispatcher_owner SET lease_expires_at='2999-01-01T00:00:00Z'",
        }
        assert uow.connection.execute(mutations[change]).rowcount > 0
    with pytest.raises(ValueError, match=message):
        migrate_execution_catalog(deps.config.db_path,tmp_path/"migration-backup")
