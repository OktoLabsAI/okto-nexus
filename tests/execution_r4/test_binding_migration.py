"""Reviewed embedded adoption preserves legacy endpoint identity and denials."""
import json
import pytest
from okto_nexus.adapters.outbound.sqlite.migration_backup import create_migration_backup
from okto_nexus.bootstrap.execution_migration import migrate_execution_catalog
from okto_nexus.domain.ids import resolve_workspace_id
import test_local_realization as local
from test_binding_operator import prepare_operator


@pytest.fixture
def adopted_setup(tmp_path, monkeypatch, request):
    original = local.app_for
    def seeded(home):
        deps, app = original(home)
        root = tmp_path/"workspace"
        workspace = resolve_workspace_id(str(root))
        with deps.connection_factory.unit_of_work() as uow:
            c=uow.connection
            c.execute("INSERT INTO agents(agent_id,created_at) VALUES('subject','2026-10-01')")
            app.state.test_existing_keys = {
                actor: app.state.auth.issue_key(uow, agent_id=actor)
                for actor in ("operator", "subject")
            }
            c.execute("INSERT INTO workspaces(workspace_id,root_realpath,created_at) VALUES(?,?,'2026-10-01')",
                      (workspace,str(root.resolve())))
            c.execute("INSERT INTO runtime_profiles(profile_id,adapter_id,config,created_at,updated_at) "
                      "VALUES('legacy-profile','codex',?,'2026-10-01','2026-10-01')",
                      (json.dumps({"command":"historical-command"}),))
            c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,"
                      "enabled,activation_state,public_config,created_at,updated_at) "
                      "VALUES('legacy-endpoint','subject',?,'codex','legacy','legacy-profile',0,'denied',?,'2026-10-01','2026-10-01')",
                      (workspace,json.dumps({"historical":True})))
        backup=tmp_path/"migration-backup"
        create_migration_backup(deps.config.db_path,backup)
        assert migrate_execution_catalog(deps.config.db_path,backup)["status"]=="CATALOG_BACKFILL_COMPLETE"
        app.state.test_legacy_workspace=workspace
        return deps,app
    monkeypatch.setattr(local,"app_for",seeded)
    yield from local.local_setup.__wrapped__(tmp_path,monkeypatch,request)


def proposal_request(setup):
    _, app, _, _, body, _, _=setup
    response=local.publish(setup,changes={"workspace_id":app.state.test_legacy_workspace})
    assert response.status_code==201,response.text
    view=response.json()
    return dict(client_intent_id="adopt",agent_id_hint="subject",executor_id=view["executor_id"],
        adapter_id=body["adapter_id"],candidate_ref=body["candidate_ref"],
        inventory_revision=body["inventory_revision"],realization_ref=view["realization_ref"],
        workspace_id=view["workspace_id"],alias="adopted",adopt_endpoint_id="legacy-endpoint")


def test_reviewed_adoption_preserves_endpoint_and_disabled_policy(adopted_setup):
    deps,_,client,headers,*_=adopted_setup
    body=proposal_request(adopted_setup)
    from pathlib import Path
    from jsonschema import Draft202012Validator
    schema=json.loads((Path(__file__).parents[2]/"plans/contratos/http-target.schema.json").read_text())
    Draft202012Validator({"$defs":schema["$defs"],"$ref":"#/$defs/BindingPrepareRequest"}).validate(body)
    proposal,apply=prepare_operator(client,headers,body)
    assert proposal["endpoint_id"]=="legacy-endpoint"
    assert "Preserve enabled=False and activation_state=denied" in proposal["diff"]["summary"]
    assert "enabled" not in proposal["diff"]["fields_changed"]
    response=client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"])
    assert response.status_code==200,response.text
    assert response.json()["endpoint_id"]=="legacy-endpoint"
    assert client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"]).json()==response.json()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        c=uow.connection
        endpoint=dict(c.execute("SELECT * FROM agent_endpoints").fetchone())
        assert endpoint["endpoint_id"]=="legacy-endpoint"
        assert (endpoint["enabled"],endpoint["activation_state"])==(0,"denied")
        assert endpoint["adapter_id"]=="codex_app_server" and endpoint["revision"]==2
        assert json.loads(endpoint["public_config"])=={"historical":True,"alias":"adopted"}
        assert json.loads(c.execute("SELECT config FROM runtime_profiles WHERE profile_id='legacy-profile'").fetchone()[0])=={"command":"historical-command"}
        assert c.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0]==0
        assert c.execute("SELECT state FROM execution_migration_map WHERE source_type='agent_endpoints'").fetchone()[0]=="BINDING_ADOPTED"


@pytest.mark.parametrize("change",["endpoint","mapping","session"])
def test_adoption_revalidates_source_and_legacy_session_after_review(adopted_setup,change):
    deps,_,client,headers,*_=adopted_setup
    _,apply=prepare_operator(client,headers,proposal_request(adopted_setup))
    with deps.connection_factory.unit_of_work() as uow:
        c=uow.connection
        if change=="endpoint":
            c.execute("UPDATE agent_endpoints SET revision=revision+1")
        elif change=="mapping":
            c.execute("UPDATE execution_migration_map SET state='MIGRATION_REVIEW_REQUIRED' WHERE source_type='agent_endpoints'")
        else:
            c.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,started_at,created_at,updated_at,endpoint_id) "
                      "VALUES('uncertain','codex','subject','running','{}','2026-10-01','2026-10-01','2026-10-01','legacy-endpoint')")
    response=client.post("/v1/connections/bindings:apply",json=apply,headers=headers["operator"])
    assert response.status_code==409,response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0]==0


def test_agent_cannot_adopt_legacy_endpoint(adopted_setup):
    _,_,client,headers,*_=adopted_setup
    response=client.post("/v1/connections/bindings:prepare",json=proposal_request(adopted_setup),
                         headers=headers["subject"])
    assert response.status_code==403,response.text


@pytest.mark.parametrize("state", ["protocol_ready", "outcome_unknown"])
def test_canonical_adapter_cannot_bypass_legacy_cutover(adopted_setup, state):
    deps, _, client, headers, *_ = adopted_setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO harness_sessions(session_id,kind,owning_agent_id,status,capabilities,"
            "started_at,created_at,updated_at,endpoint_id,lifecycle_state) "
            "VALUES('old-owner','codex','subject','running','{}','2026-10-01','2026-10-01','2026-10-01',"
            "'legacy-endpoint',?)", (state,))
    body = proposal_request(adopted_setup)
    body.pop("adopt_endpoint_id")
    proposal, apply = prepare_operator(client, headers, body)
    assert proposal["can_apply"] is False
    response = client.post("/v1/connections/bindings:apply", json=apply, headers=headers["operator"])
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_bindings").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM agent_endpoints").fetchone()[0] == 1
        assert uow.connection.execute("SELECT lifecycle_state FROM harness_sessions WHERE session_id='old-owner'").fetchone()[0] == state
