"""UI-005 inputs, not future Home DTOs or execution qualification.

The first session/question uses real admission, WSS, lease and event ingress.
Additional read facts are deliberately synthetic; no native binary is executed.
All rows share the installation returned by that admission fixture.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import sqlite3
from threading import Event, get_ident
from types import SimpleNamespace

import pytest


class ControlledClock:
    def __init__(self, instant="2026-11-16T12:00:00.000000Z"):
        self.instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))

    def now_iso(self):
        return self.instant.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def now_epoch(self):
        return self.instant.timestamp()

    def advance(self, seconds):
        self.instant += timedelta(seconds=seconds)


class ReadBarrier:
    """Explicit rendezvous for future browser delayed reads; never a sleep."""
    def __init__(self):
        self.entered, self.release = Event(), Event()

    def wait(self, timeout=5):
        self.entered.set()
        if not self.release.wait(timeout):
            raise TimeoutError("UI fixture barrier was not released")


@dataclass(frozen=True)
class ConnectionFact:
    """Persisted test context, NOT a product ConnectionRef/readiness claim."""
    server_id: str
    executor_id: str
    binding_id: str
    workspace_id: str
    workspace_binding_id: str
    agent_id: str
    provenance: str


@dataclass
class Scenario:
    deps: object
    app: object
    clock: ControlledClock
    connections: tuple[ConnectionFact, ConnectionFact]
    sessions: tuple[str, str]
    question_recipient: str
    decision_body: dict
    external: dict

    @property
    def factory(self):
        return self.deps.connection_factory

    @property
    def operator(self):
        from okto_nexus.domain.runtime_context import RuntimeRequestContext
        return RuntimeRequestContext("operator", "http_loopback", trusted_local_operator=True)

    def read(self, **kwargs):
        return self.app.state.home.read(context=self.operator, **kwargs)

    @contextmanager
    def partial_work(self):
        """Fail the real SQL port, leaving other actual sources readable."""
        queries = self.app.state.home.queries
        original_page, original_overview = queries.page, queries.overview

        def page(uow, **kwargs):
            if kwargs["section"] == "work":
                raise sqlite3.OperationalError("controlled UI fixture work source failure")
            return original_page(uow, **kwargs)

        def overview(*args, **kwargs):
            raise sqlite3.OperationalError("controlled UI fixture overview failure")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(queries, "page", page)
            patch.setattr(queries, "overview", overview)
            yield
        assert queries.overview == original_overview

    def baseline(self):
        """One current overview sample. Counts trace SQL incl. nested reads.

        This is not a latency benchmark or a future entries/navigation result.
        """
        statements, uows = [], []
        original = self.factory.unit_of_work
        reader_thread = get_ident()

        @contextmanager
        def traced(*args, **kwargs):
            if get_ident() != reader_thread:
                with original(*args, **kwargs) as uow:
                    yield uow
                return
            uows.append(kwargs)
            with original(*args, **kwargs) as uow:
                c = uow.connection
                c.set_trace_callback(statements.append)
                before = c.total_changes
                try:
                    yield uow
                    assert c.total_changes == before
                finally:
                    c.set_trace_callback(None)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(self.factory, "unit_of_work", traced)
            payload = self.read()
        return dict(contract="current_home_overview", samples=1, read_uows=len(uows),
                    all_read_only=all(k == {"write": False} for k in uows),
                    sql_statements=len(statements), writes=0,
                    payload_bytes=len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()),
                    sections={k: payload[k]["status"] for k in
                              ("work", "results", "agents", "attention", "external_activity")})


def _copy(c, table, row, **changes):
    value = dict(row, **changes)
    c.execute("INSERT INTO " + table + "(" + ",".join(value) + ") VALUES(" +
              ",".join("?" for _ in value) + ")", tuple(value.values()))


def _read_facts(deps, resolution):
    """Adapt old HOME seed to returned installation; never copy another DB."""
    factory, now = deps.connection_factory, deps.clock.now_iso()
    scope = resolution["scope"]
    with factory.unit_of_work() as uow:
        c = uow.connection
        for agent in ("B", "C"):
            deps.repos.agents.upsert(uow, agent_id=agent, role="worker")
        for i, (sender, recipient) in enumerate((("subject", "B"), ("B", "C"))):
            c.execute("INSERT INTO messages(message_id,workspace_id,from_agent_id,body,created_at) VALUES(?, 'ws',?,?,?)",
                      (f"ui-message-{i}", sender, "Synthetic coordination", now))
            c.execute("INSERT INTO message_deliveries(delivery_id,message_id,recipient_agent_id,status,created_at) VALUES(?,?,?,'unread',?)",
                      (f"ui-delivery-{i}", f"ui-message-{i}", recipient, now))
            c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,created_at,updated_at) VALUES(?,'ws',?,?,'eligible','OPEN',?,?)",
                      (f"ui-handoff-{i}", sender, json.dumps({"strategy": "direct", "agent_id": recipient}), now, now))
        c.execute("INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,created_at,updated_at) VALUES('ui-unassigned','ws','subject',?,'eligible','OPEN',?,?)",
                  ('{"strategy":"broadcast"}', now, now))
        opening = c.execute("SELECT * FROM execution_operations WHERE action='runtime.open'").fetchone()
        _copy(c, "execution_operations", opening, operation_id="ui-open-2", binding_id="ui-binding-2",
              session_id="ui-session-2", admission_state="RESOLVED_TERMINAL")
        session = c.execute("SELECT * FROM execution_sessions WHERE session_id=?", (scope["session_id"],)).fetchone()
        _copy(c, "execution_sessions", session, session_id="ui-session-2", binding_id="ui-binding-2",
              open_operation_id="ui-open-2", lifecycle_state="CLOSED", lease_state="CLOSED",
              stream_epoch="ui-historical-epoch")
        turn = c.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone()
        for operation, stage in (("ui-unknown", "OUTCOME_UNKNOWN"), ("ui-success", "SUCCEEDED")):
            _copy(c, "execution_operations", turn, operation_id=operation, binding_id="ui-binding-2",
                  session_id="ui-session-2", admission_state="RESOLVED_TERMINAL")
            c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,?,1,0,?)",
                      (scope["server_id"], scope["executor_id"], operation, turn["intent_hash"], stage, now))
        c.execute("INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,opening_operation_id,opening_intent_hash,request_json,state,recorded_at) VALUES(?,?,'ui-session-2',1,'ui-open-2',?,'{}','REQUESTED',?)",
                  (scope["server_id"], scope["executor_id"], opening["intent_hash"], now))
        c.execute("UPDATE agents SET api_key_hash='synthetic-ui-B',permissions=? WHERE agent_id='B'",
                  (json.dumps({"observations": {"manage_self": True, "publish": True}}),))
    deps.config.feature_observations = True
    from okto_nexus.application.observations import ObservationService
    from okto_nexus.application.runtime_access import RuntimeAccessService
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    access = RuntimeAccessService(connection_factory=factory, agents=deps.repos.agents,
        endpoints=None, grants=None, config=deps.config, clock=deps.clock)
    observations = ObservationService(deps=deps, access=access)
    operator = RuntimeRequestContext("operator", "http_loopback", trusted_local_operator=True)
    source = observations.create_source(context=operator, body=dict(agent_id="B", source_kind="custom",
        workspace_ids=["ws"], registration_ref="ui-fixture"))["source"]
    instance = observations.create_instance(context=operator, source_id=source["source_id"], body=dict(
        expected_revision=source["revision"], workspace_id="ws", external_instance_ref="ui-fixture-instance"))["instance"]
    token = observations.issue_token(context=operator, source_id=source["source_id"], body=dict(
        expected_revision=source["revision"], instance_grants=[dict(observed_instance_id=instance["observed_instance_id"],
        generation=instance["generation"])]))["token"]
    observations.publish(token=token, payload=dict(schema_version=1, source_id=source["source_id"],
        observed_instance_id=instance["observed_instance_id"], generation=instance["generation"], sequence=1,
        state="working", evidence="reported", observed_at=now))
    return dict(source_id=source["source_id"], observed_instance_id=instance["observed_instance_id"])


@contextmanager
def scenario(directory: Path, *, recipient="operator", clock=None):
    """Own finite scenario. Directory must be new/empty; caller owns removal.

    Two persisted connections/sessions, one *live admitted* question session,
    one closed synthetic historical session. Aliases A/B/C mean subject/B/C.
    Recipient variants exercise the actual native authority independently.
    """
    directory = Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("UI fixture requires an empty explicit directory")
    if recipient not in {"operator", "subject"}:
        raise ValueError("recipient must be operator or subject")
    directory.mkdir(parents=True, exist_ok=True)
    tests = Path(__file__).resolve().parents[2] / "tests"
    clock = clock or ControlledClock()
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(tests / "execution_r4"))
        opening_module = importlib.import_module("test_open_bootstrap")
        native = importlib.import_module("test_native_decisions")
        dependencies = importlib.import_module("okto_nexus.bootstrap.dependencies")
        inventory = importlib.import_module("okto_nexus.bootstrap.embedded_inventory")
        patch.setattr(dependencies, "SystemClock", lambda: clock)
        patch.setattr(inventory, "discover_local_candidates", lambda *a, **k: [])
        original_setup = opening_module.setup_authority

        def setup(*args, **kwargs):
            state = original_setup(*args, **kwargs)
            with state[0].connection_factory.unit_of_work() as uow:
                c = uow.connection
                endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='ep'").fetchone()
                _copy(c, "agent_endpoints", endpoint, endpoint_id="ui-ep-2")
                binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='binding'").fetchone()
                _copy(c, "execution_bindings", binding, binding_id="ui-binding-2", endpoint_id="ui-ep-2")
            from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
            from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
            state = list(state)
            _, state[7], _ = current_agent_revisions(state[0].connection_factory, agent_id="subject")
            state[9] = issue_execution_ticket(state[0].connection_factory, server_id=state[10],
                executor_id=state[11], binding_id="binding", agent_id="subject",
                scopes=frozenset({"lane:attach", "lease:request"})).ticket
            return tuple(state)

        patch.setattr(opening_module, "setup_authority", setup)
        gen = opening_module.opening.__wrapped__(directory, patch, SimpleNamespace(param={"max_executions": 10}))
        opened = next(gen)
        deps = opened[0]
        try:
            _, app, decision = native.decision_state.__wrapped__(opened, SimpleNamespace(
                param="input" if recipient == "operator" else "agent_input"))
            external = _read_facts(deps, opened[6])
            scope = opened[6]["scope"]
            connections = tuple(ConnectionFact(scope["server_id"], scope["executor_id"], binding,
                "ws", "wxb", "subject", provenance) for binding, provenance in
                (("binding", "canonical-admission"), ("ui-binding-2", "synthetic-read-fact")))
            yield Scenario(deps, app, clock, connections, (scope["session_id"], "ui-session-2"),
                           recipient, decision, external)
        finally:
            gen.close()
            deps.connection_factory.close()
