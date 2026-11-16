"""Reusable real-SQLite inputs for HOME-R1, not a future Home read model.

Identities/sessions/OBS use existing application/repository contracts. Handoffs,
attempts and execution facts are synthetic read-model inputs, inserted against
the migrated schema; they do not claim that a native execution took place.
No database, credential, message body or event payload belongs in public evidence.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.observability_repo import SqliteObservabilityQueries
from okto_nexus.application.observability import ObservabilityService
from okto_nexus.application.observations import ObservationService
from okto_nexus.application.runtime_access import RuntimeAccessService
from okto_nexus.bootstrap.dependencies import build_repos
from okto_nexus.domain.base import iso_to_epoch
from okto_nexus.domain.runtime_context import RuntimeRequestContext


OPERATOR = RuntimeRequestContext(None, "http_loopback", trusted_local_operator=True)
WORKSPACES = ("home-alpha", "home-beta")
BASE_AGENTS = ("global", "A", "B", "C", "operator", "revoked")


@dataclass
class HomeScenario:
    factory: object
    config: object
    clock: object
    repos: object
    graph: ObservabilityService
    observations: ObservationService
    agent_ids: tuple[str, ...]
    source_id: str = ""
    observed_instance_id: str = ""

    def advance(self, seconds):
        now = datetime.fromisoformat(self.clock.now_iso().replace("Z", "+00:00"))
        self.clock.set_iso((now + timedelta(seconds=seconds)).isoformat(
            timespec="microseconds").replace("+00:00", "Z"))
        self.clock.tick(seconds)

    def graph_snapshot(self, workspace_id=WORKSPACES[0]):
        with self.factory.unit_of_work(write=False) as uow:
            return self.graph.graph_snapshot(uow, workspace_id=workspace_id)

    def counts(self):
        with self.factory.unit_of_work(write=False) as uow:
            return {table: uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("agents", "workspaces", "sessions", "handoffs",
                                  "handoff_runtime_attempts", "events")}


def _execution_cleanup(c, now):
    """Successful work plus an independent unresolved cleanup obligation."""
    c.execute("INSERT INTO execution_executors(server_id,executor_id,kind,control_state,generation) "
              "VALUES('fixture-server','fixture-executor','embedded','CONTROL_READY',1)")
    c.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,enabled,activation_state,created_at,updated_at) "
              "VALUES('fixture-endpoint','B',?,'fixture','nxl-r4',1,'approved',?,?)", (WORKSPACES[0], now, now))
    c.execute("INSERT INTO execution_workspace_bindings(server_id,workspace_binding_id,executor_id,workspace_id,realization_handle,revision,status) "
              "VALUES('fixture-server','fixture-wb','fixture-executor',?,'fixture-local',1,'ACTIVE')", (WORKSPACES[0],))
    c.execute("INSERT INTO execution_bindings(server_id,binding_id,executor_id,endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,realization_ref,realization_revision,binding_revision) "
              "VALUES('fixture-server','fixture-binding','fixture-executor','fixture-endpoint','fixture-wb','fixture-candidate','fixture-inventory','fixture-realization',1,1)")
    c.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at) "
              "VALUES('fixture-server','fixture-executor','fixture-success','B','A','fixture-binding',?,'fixture-wb','fixture-native-session','turn.submit','fixture-digest','{}','{}','RESOLVED_TERMINAL',?)", (WORKSPACES[0], now))
    c.execute("INSERT INTO execution_operations(server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,expected_revisions_json,admission_state,created_at) "
              "VALUES('fixture-server','fixture-executor','fixture-open','B','A','fixture-binding',?,'fixture-wb','fixture-native-session','runtime.open','fixture-opening-digest','{}','{}','RESOLVED_TERMINAL',?)", (WORKSPACES[0], now))
    c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) "
              "VALUES('fixture-server','fixture-executor','fixture-success',1,'fixture-digest','SUCCEEDED',1,0,?)", (now,))
    c.execute("INSERT INTO execution_sessions(server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,open_operation_id,owner_generation,lifecycle_state,lease_state) "
              "VALUES('fixture-server','fixture-executor','fixture-native-session','fixture-binding',?,'fixture-wb','fixture-open',1,'READY','ACTIVE')", (WORKSPACES[0],))
    c.execute("INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,opening_operation_id,opening_intent_hash,request_json,state,recorded_at) "
              "VALUES('fixture-server','fixture-executor','fixture-native-session',1,'fixture-open','fixture-opening-digest','{}','REQUESTED',?)", (now,))


def seed_scenario(factory, config, clock, *, agents=6, activities=6, events=20):
    """Scale independently to 100/1,000/100,000 without allocating event history.

    ``activities`` counts synthetic handoff inputs, not an implemented unified
    Home activity entity. ``events`` is extra bulk history plus one OBS event.
    """
    if agents < len(BASE_AGENTS) or activities < 3 or events < 0:
        raise ValueError("scenario requires six agents, three activities and nonnegative history")
    clock.tick(iso_to_epoch(clock.now_iso()) - clock.now_epoch())
    config.feature_observations = True
    repos, emitter = build_repos(clock, config)
    access = RuntimeAccessService(connection_factory=factory, agents=repos.agents,
        endpoints=None, grants=None, config=config, clock=clock)
    observations = ObservationService(deps=SimpleNamespace(connection_factory=factory,
        config=config, clock=clock, repos=repos, event_emitter=emitter), access=access)
    names = BASE_AGENTS + tuple(f"scale-{i:03d}" for i in range(agents - len(BASE_AGENTS)))
    scenario = HomeScenario(factory, config, clock, repos,
        ObservabilityService(SqliteObservabilityQueries(), clock, config), observations, names)
    now = clock.now_iso()
    with factory.unit_of_work() as uow:
        c = uow.connection
        for workspace in WORKSPACES:
            repos.workspaces.upsert(uow, workspace_id=workspace)
        for agent in names:
            repos.agents.upsert(uow, agent_id=agent, role="worker")
        c.execute("UPDATE agents SET is_active=0,permissions='{}' WHERE agent_id='revoked'")
        # A fake binding marker is required by the existing OBS availability
        # contract. It is not a user credential and never authenticates HTTP.
        c.execute("UPDATE agents SET api_key_hash='fixture-only-A',permissions=? WHERE agent_id='A'",
                  (json.dumps({"observations": {"manage_self": True, "publish": True}}),))
        for sid, agent, workspace in (("a-alpha", "A", WORKSPACES[0]),
                                      ("a-beta", "A", WORKSPACES[1]),
                                      ("b-alpha", "B", WORKSPACES[0]),
                                      ("c-beta", "C", WORKSPACES[1])):
            repos.sessions.create(uow, session_id=sid, agent_id=agent,
                                  workspace_id=workspace, status="active")
        for index, (sender, recipient, workspace) in enumerate(
                (("A", "B", WORKSPACES[0]), ("B", "C", WORKSPACES[0]), ("C", "A", WORKSPACES[1]))):
            c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?,?,?,?,?)",
                      (f"fixture-message-{index}", workspace, sender, "synthetic coordination", now))
            c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,?,?,?,?)",
                      (f"fixture-delivery-{index}", f"fixture-message-{index}", recipient, "unread", now))
        c.executemany("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            ((f"fixture-handoff-{i:04d}", WORKSPACES[i % 2], "A" if i % 2 == 0 else "B",
              json.dumps({"strategy": "broadcast"}), "eligible", "OPEN", now, now) for i in range(activities)))
        for i, state in enumerate(("NOT_AVAILABLE", "CANCELLED_NO_EFFECT", "WAITING")):
            c.execute("INSERT INTO handoff_runtime_attempts(attempt_id,workspace_id,handoff_id,agent_id,claim_generation,principal_json,request_json,state,disposition,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"fixture-attempt-{i}", WORKSPACES[0], "fixture-handoff-0000", "B", i,
                       '{"fixture":true}', '{"fixture":true}', state, "ACQUIRE", int(i == 2), now, now))
        _execution_cleanup(c, now)
        c.executemany("INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,created_at) VALUES(?,?,?,?,?,?,?)",
            ((WORKSPACES[i % 2], "home-fixture", "fixture.activity", names[1 + i % (len(names) - 1)],
              '{"fixture":true}', "public", now) for i in range(events)))
    source = observations.create_source(context=OPERATOR, body=dict(agent_id="A", source_kind="custom",
        workspace_ids=[WORKSPACES[0]], registration_ref="home-fixture"))["source"]
    instance = observations.create_instance(context=OPERATOR, source_id=source["source_id"], body=dict(
        expected_revision=source["revision"], workspace_id=WORKSPACES[0], external_instance_ref="home-fixture-instance"))["instance"]
    token = observations.issue_token(context=OPERATOR, source_id=source["source_id"], body=dict(
        expected_revision=source["revision"], instance_grants=[dict(observed_instance_id=instance["observed_instance_id"],
        generation=instance["generation"])]))["token"]
    observations.publish(token=token, payload=dict(schema_version=1, source_id=source["source_id"],
        observed_instance_id=instance["observed_instance_id"], generation=instance["generation"], sequence=1,
        state="working", evidence="reported", observed_at=now))
    scenario.source_id, scenario.observed_instance_id = source["source_id"], instance["observed_instance_id"]
    return scenario


@pytest.fixture
def home_scenario(migrated_factory, tmp_config, fake_clock):
    return seed_scenario(migrated_factory, tmp_config, fake_clock)
