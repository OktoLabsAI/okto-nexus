"""Tests for communication guardrails and explicit agent groups."""

from __future__ import annotations

import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.outbound.file.artifacts import LocalArtifactStore
from okto_nexus.adapters.outbound.file.store import WorkspaceFileStore
from okto_nexus.adapters.outbound.sqlite.artifacts_repo import SqliteArtifactRepo
from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.guardrails_repo import (
    SqliteAgentGroupRepo,
    SqliteGuardrailAssignmentRepo,
    SqliteGuardrailRepo,
)
from okto_nexus.adapters.outbound.sqlite.handoff_repo import SqliteHandoffRepo
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.artifacts import ArtifactService
from okto_nexus.application.guardrails import (
    GUARDRAIL_DENIED_EVENT,
    GuardrailService,
)
from okto_nexus.application.handoff import HandoffService
from okto_nexus.application.messages import MessageService
from okto_nexus.domain import guardrails as gr
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.domain.policy import validate_agent_bindings
from okto_nexus.domain.routing import RoutingAgent, is_agent_eligible
from okto_nexus.errors import ErrorCode, OktoNexusError


class _Clock:
    def now_iso(self) -> str:
        return "2026-07-06T20:00:00.000000Z"

    def now_epoch(self) -> float:
        return 1.0


class _ExactTokenizer:
    encoding = "o200k_base"

    def count(self, text):
        return 0 if not text else len(str(text).split())

    def count_for_message(self, message_id, body):
        return self.count(body)


class _ApproxTokenizer:
    encoding = "approx-chars-v1"

    def count(self, text):
        return 1

    def count_for_message(self, message_id, body):
        return self.count(body)


class _ExplodingEmitter:
    def emit(self, *args, **kwargs):
        raise RuntimeError("audit sink down")


class _Server:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture()
def guardrail_rest_client(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key

    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    app = build_app(deps)
    with TestClient(app) as client:
        client.headers.update({"x-api-key": operator_key})
        yield client, deps


def _issue_key(deps, agent_id: str) -> str:
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        return auth.issue_key(uow, agent_id=agent_id)


def _seed_agent(uow, agent_id: str, *, capabilities=None) -> None:
    SqliteAgentRepo().upsert(
        uow,
        agent_id=agent_id,
        role="worker",
        capabilities=capabilities,
    )


def _routing_agent(agent_id: str = "alpha") -> RoutingAgent:
    return RoutingAgent(
        agent_id=agent_id,
        workspace_id="ws_guardrails",
        role="worker",
        capabilities=[],
    )


def _make_active_guardrail(repo, uow, guardrail_id: str = "gr_1") -> None:
    repo.create(
        uow,
        guardrail_id=guardrail_id,
        name=f"Guardrail {guardrail_id}",
        description="deny unsafe communication",
    )
    repo.add_version(
        uow,
        guardrail_id=guardrail_id,
        status=gr.VERSION_STATUS_ACTIVE,
        evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
        evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
        surfaces=["message", "handoff"],
        field_targets=["body", "payload"],
    )


def _seed_workspace(uow, workspace_id: str = "ws_guardrails") -> None:
    SqliteWorkspaceRepo(_Clock()).upsert(
        uow,
        workspace_id=workspace_id,
        display_name="Guardrails",
        root_realpath="D:\\guardrails",
    )


def _service(migrated_factory, *, tokenizer=None, emitter=None) -> GuardrailService:
    clock = _Clock()
    return GuardrailService(
        connection_factory=migrated_factory,
        assignments=SqliteGuardrailAssignmentRepo(clock),
        agents=SqliteAgentRepo(clock),
        clock=clock,
        tokenizer=tokenizer or _ExactTokenizer(),
        event_emitter=emitter
        if emitter is not None
        else SqliteEventEmitter(SqliteEventRepo(clock)),
    )


def _events(migrated_factory, event_type: str = GUARDRAIL_DENIED_EVENT):
    with migrated_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT type, payload FROM events WHERE type = ? ORDER BY event_id",
            (event_type,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def _count(migrated_factory, table: str) -> int:
    conn = migrated_factory.get_connection()
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def _event_count(migrated_factory, event_type: str) -> int:
    conn = migrated_factory.get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = ?",
            (event_type,),
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def _project(tmp_path) -> tuple[str, str]:
    root = tmp_path / "project"
    root.mkdir()
    return str(root), resolve_workspace_id(str(root))


def _add_guardrail(
    uow,
    *,
    guardrail_id: str,
    evaluator_kind: str = gr.EVALUATOR_KIND_DETERMINISTIC,
    evaluator_config: dict,
    mode: str = gr.ENFORCEMENT_MODE_ENFORCE,
    surfaces=("message",),
    field_targets=("body",),
) -> None:
    repo = SqliteGuardrailRepo(_Clock())
    assignments = SqliteGuardrailAssignmentRepo(_Clock())
    repo.create(uow, guardrail_id=guardrail_id, name=guardrail_id)
    repo.add_version(
        uow,
        guardrail_id=guardrail_id,
        status=gr.VERSION_STATUS_ACTIVE,
        evaluator_kind=evaluator_kind,
        evaluator_config=evaluator_config,
        surfaces=surfaces,
        field_targets=field_targets,
    )
    assignments.create(
        uow,
        assignment_id=f"asg_{guardrail_id}",
        scope_kind=gr.SCOPE_KIND_GLOBAL,
        group_id=None,
        guardrail_id=guardrail_id,
        version_mode=gr.VERSION_MODE_LATEST,
        mode=mode,
    )


def _insert_unvalidated_active_guardrail(
    uow,
    *,
    guardrail_id: str,
    evaluator_kind: str,
    evaluator_config: dict,
) -> None:
    """Simulate legacy/corrupt rows to retain runtime fail-closed coverage."""

    SqliteGuardrailRepo(_Clock()).create(
        uow,
        guardrail_id=guardrail_id,
        name=guardrail_id,
    )
    now = _Clock().now_iso()
    uow.connection.execute(
        """
        INSERT INTO guardrail_versions (
            guardrail_id, version, status, evaluator_kind, evaluator_config,
            surfaces, field_targets, created_at, updated_at, activated_at
        ) VALUES (?, 1, 'active', ?, ?, '["message"]', '["body"]', ?, ?, ?)
        """,
        (guardrail_id, evaluator_kind, json.dumps(evaluator_config), now, now, now),
    )
    SqliteGuardrailAssignmentRepo(_Clock()).create(
        uow,
        assignment_id=f"asg_{guardrail_id}",
        scope_kind=gr.SCOPE_KIND_GLOBAL,
        group_id=None,
        guardrail_id=guardrail_id,
        version_mode=gr.VERSION_MODE_LATEST,
        mode=gr.ENFORCEMENT_MODE_ENFORCE,
    )


def _assert_scrubbed(payload, raw_text="secret"):
    forbidden = {
        "subject",
        "body",
        "payload",
        "content",
        "acceptance_criteria",
        "excerpt",
        "keyword",
        "capture",
        "pii",
    }
    assert forbidden.isdisjoint(payload)
    assert raw_text not in json.dumps(payload, sort_keys=True)


def test_migrations_create_guardrail_group_and_capability_scope(migrated_factory):
    conn = migrated_factory.get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        versions = [
            row["version"]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        assignment_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(guardrail_assignments)")
        }
    finally:
        conn.close()

    assert 25 in versions
    assert 27 in versions
    assert "capability" in assignment_columns
    assert {
        "agent_groups",
        "agent_group_members",
        "guardrails",
        "guardrail_versions",
        "guardrail_assignments",
    } <= tables


def test_groups_are_rosters_and_latest_active_resolution_is_scoped(
    migrated_factory,
):
    groups = SqliteAgentGroupRepo()
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        _seed_agent(uow, "alpha")
        _seed_agent(uow, "beta")
        groups.create(uow, group_id="grp_reviewers", name="Reviewers")
        groups.add_member(uow, group_id="grp_reviewers", agent_id="alpha")

        guardrails.create(uow, guardrail_id="gr_pii", name="PII")
        guardrails.add_version(
            uow,
            guardrail_id="gr_pii",
            status=gr.VERSION_STATUS_DRAFT,
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "regex", "patterns": ["draft"]},
            surfaces=["message"],
            field_targets=["body"],
        )
        guardrails.add_version(
            uow,
            guardrail_id="gr_pii",
            status=gr.VERSION_STATUS_ACTIVE,
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "regex", "patterns": ["ssn"]},
            surfaces=["message"],
            field_targets=["body"],
        )

        assignments.create(
            uow,
            assignment_id="asg_global",
            scope_kind=gr.SCOPE_KIND_GLOBAL,
            group_id=None,
            guardrail_id="gr_pii",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_WARN,
            priority=20,
        )
        assignments.create(
            uow,
            assignment_id="asg_group",
            scope_kind=gr.SCOPE_KIND_AGENT_GROUP,
            group_id="grp_reviewers",
            guardrail_id="gr_pii",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_ENFORCE,
            priority=10,
        )

        alpha = assignments.effective_for_agent(uow, agent_id="alpha")
        beta = assignments.effective_for_agent(uow, agent_id="beta")
        alpha_groups = groups.groups_for_agent(uow, agent_id="alpha")
        alpha_tags = uow.connection.execute(
            "SELECT tags FROM agents WHERE agent_id = 'alpha'"
        ).fetchone()["tags"]

    assert alpha_groups == ["grp_reviewers"]
    assert alpha_tags is None  # group membership did not mutate agent tags
    assert [item.assignment.assignment_id for item in alpha] == [
        "asg_group",
        "asg_global",
    ]
    assert [item.version.version for item in alpha if item.version] == [2, 2]
    assert [item.assignment.assignment_id for item in beta] == ["asg_global"]
    assert beta[0].version and beta[0].version.version == 2


def test_capability_assignment_follows_announced_agent_capabilities(
    migrated_factory,
):
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO capability_names (name, description, created_at) "
            "VALUES ('review', 'Can review sensitive output', ?)",
            (_Clock().now_iso(),),
        )
        _seed_agent(uow, "reviewer", capabilities={"review": True})
        _seed_agent(uow, "builder", capabilities={"build": True})
        _make_active_guardrail(guardrails, uow, "gr_review")
        assignments.create(
            uow,
            assignment_id="asg_review_capability",
            scope_kind=gr.SCOPE_KIND_CAPABILITY,
            group_id=None,
            capability="review",
            guardrail_id="gr_review",
            mode=gr.ENFORCEMENT_MODE_AUDIT,
        )

        reviewer = assignments.effective_for_agent(uow, agent_id="reviewer")
        builder = assignments.effective_for_agent(uow, agent_id="builder")

    assert [item.assignment.assignment_id for item in reviewer] == [
        "asg_review_capability"
    ]
    assert reviewer[0].assignment.capability == "review"
    assert builder == []


def test_agent_group_is_not_a_message_target_strategy():
    with pytest.raises(OktoNexusError) as exc:
        is_agent_eligible(
            _routing_agent("alpha"),
            {"strategy": "group", "group_id": "grp_reviewers"},
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR.value


def test_guardrail_service_strictest_wins_cross_scope_same_version(
    migrated_factory,
):
    groups = SqliteAgentGroupRepo()
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        groups.create(uow, group_id="grp_sensitive", name="Sensitive")
        groups.add_member(uow, group_id="grp_sensitive", agent_id="alpha")
        _make_active_guardrail(guardrails, uow, "gr_strict")
        assignments.create(
            uow,
            assignment_id="asg_global_audit",
            scope_kind=gr.SCOPE_KIND_GLOBAL,
            group_id=None,
            guardrail_id="gr_strict",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_AUDIT,
            priority=10,
        )
        assignments.create(
            uow,
            assignment_id="asg_group_enforce",
            scope_kind=gr.SCOPE_KIND_AGENT_GROUP,
            group_id="grp_sensitive",
            guardrail_id="gr_strict",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_ENFORCE,
            priority=20,
        )

    svc = _service(migrated_factory)
    with migrated_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError) as denied:
            svc.enforce(
                uow,
                workspace_id="ws_guardrails",
                actor_agent_id="alpha",
                surface="message_create",
                fields={"body": "secret"},
            )

    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["assignment_id"] == "asg_group_enforce"
    assert denied.value.details["mode"] == gr.ENFORCEMENT_MODE_ENFORCE


def test_pinned_assignment_requires_active_version_and_fails_closed_later(
    migrated_factory,
):
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        _seed_agent(uow, "alpha")
        _make_active_guardrail(guardrails, uow, "gr_secret")
        guardrails.add_version(
            uow,
            guardrail_id="gr_secret",
            status=gr.VERSION_STATUS_DRAFT,
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "token_limit", "max_tokens": 10},
            surfaces=["message"],
            field_targets=["body"],
        )

        with pytest.raises(OktoNexusError) as inactive_pin:
            assignments.create(
                uow,
                assignment_id="asg_bad_pin",
                scope_kind=gr.SCOPE_KIND_GLOBAL,
                group_id=None,
                guardrail_id="gr_secret",
                version_mode=gr.VERSION_MODE_PINNED,
                pinned_version=2,
                mode=gr.ENFORCEMENT_MODE_ENFORCE,
            )
        assert inactive_pin.value.code == ErrorCode.VALIDATION_ERROR

        assignments.create(
            uow,
            assignment_id="asg_pin",
            scope_kind=gr.SCOPE_KIND_GLOBAL,
            group_id=None,
            guardrail_id="gr_secret",
            version_mode=gr.VERSION_MODE_PINNED,
            pinned_version=1,
            mode=gr.ENFORCEMENT_MODE_ENFORCE,
        )
        assert (
            assignments.effective_for_agent(uow, agent_id="alpha")[0].version.version
            == 1
        )

        guardrails.update_version_status(
            uow,
            guardrail_id="gr_secret",
            version=1,
            status=gr.VERSION_STATUS_DEPRECATED,
        )
        resolved = assignments.effective_for_agent(uow, agent_id="alpha")

    assert resolved[0].version is None
    assert resolved[0].resolution_status == gr.RESOLUTION_CONFIG_UNAVAILABLE
    assert resolved[0].reason == "pinned_version_inactive"


def test_latest_resolution_ignores_non_active_versions(migrated_factory):
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        _seed_agent(uow, "alpha")
        _make_active_guardrail(guardrails, uow, "gr_tokens")
        guardrails.add_version(
            uow,
            guardrail_id="gr_tokens",
            status=gr.VERSION_STATUS_ACTIVE,
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "token_limit", "max_tokens": 100},
            surfaces=["message"],
            field_targets=["body"],
        )
        guardrails.update_version_status(
            uow,
            guardrail_id="gr_tokens",
            version=2,
            status=gr.VERSION_STATUS_ARCHIVED,
        )
        assignments.create(
            uow,
            assignment_id="asg_latest",
            scope_kind=gr.SCOPE_KIND_GLOBAL,
            group_id=None,
            guardrail_id="gr_tokens",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_AUDIT,
        )
        resolved = assignments.effective_for_agent(uow, agent_id="alpha")
        record = guardrails.get(uow, "gr_tokens")

    assert resolved[0].version and resolved[0].version.version == 1
    assert record and record.latest_version == 2
    assert record.latest_active_version == 1


def test_assignment_fk_constraints_block_group_and_guardrail_deletion(
    migrated_factory,
):
    groups = SqliteAgentGroupRepo()
    guardrails = SqliteGuardrailRepo()
    assignments = SqliteGuardrailAssignmentRepo()

    with migrated_factory.unit_of_work() as uow:
        _seed_agent(uow, "alpha")
        groups.create(uow, group_id="grp_ops", name="Ops")
        groups.add_member(uow, group_id="grp_ops", agent_id="alpha")
        _make_active_guardrail(guardrails, uow, "gr_ops")
        assignments.create(
            uow,
            assignment_id="asg_ops",
            scope_kind=gr.SCOPE_KIND_AGENT_GROUP,
            group_id="grp_ops",
            guardrail_id="gr_ops",
            version_mode=gr.VERSION_MODE_LATEST,
            mode=gr.ENFORCEMENT_MODE_ENFORCE,
        )

        assert [
            a.assignment_id for a in assignments.list_for_group(uow, group_id="grp_ops")
        ] == ["asg_ops"]
        assert [
            a.assignment_id
            for a in assignments.list_for_guardrail(uow, guardrail_id="gr_ops")
        ] == ["asg_ops"]
        with pytest.raises(OktoNexusError) as group_delete:
            groups.delete(uow, group_id="grp_ops")
        with pytest.raises(OktoNexusError) as guardrail_delete:
            guardrails.delete(uow, guardrail_id="gr_ops")

    assert group_delete.value.code == ErrorCode.DB_ERROR
    assert guardrail_delete.value.code == ErrorCode.DB_ERROR


@pytest.mark.parametrize(
    ("guardrail_id", "config", "body", "reason"),
    [
        (
            "gr_regex",
            {"kind": "regex", "patterns": [r"secret-\d+"]},
            "contains secret-42",
            "regex_match",
        ),
        (
            "gr_keyword",
            {"kind": "keyword_blocklist", "keywords": ["secret"]},
            "contains SECRET",
            "keyword_hit",
        ),
        (
            "gr_pii",
            {"kind": "pii_detection"},
            "contact alpha@example.com",
            "pii_detected",
        ),
        (
            "gr_tokens",
            {"kind": "token_limit", "max_tokens": 1},
            "two tokens",
            "token_over_limit",
        ),
    ],
)
def test_guardrail_service_v1_evaluators_raise_guardrail_denied(
    migrated_factory, guardrail_id, config, body, reason
):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _add_guardrail(uow, guardrail_id=guardrail_id, evaluator_config=config)

    svc = _service(migrated_factory)
    with pytest.raises(OktoNexusError) as denied:
        with svc.guard(
            workspace_id="ws_guardrails",
            actor_agent_id="alpha",
            surface="message_create",
            fields={"body": body},
        ):
            raise AssertionError("denied guardrail must not yield the write UoW")

    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == reason
    assert denied.value.details["guardrail_id"] == guardrail_id
    assert denied.value.details["fingerprint"] != body
    _assert_scrubbed(denied.value.details, raw_text=body)
    events = _events(migrated_factory)
    assert len(events) == 1
    assert events[0]["reason_code"] == reason
    assert events[0]["guardrail_id"] == guardrail_id
    assert events[0]["fingerprint"] == denied.value.details["fingerprint"]
    _assert_scrubbed(events[0], raw_text=body)


def test_write_paths_deny_before_persisting_rows_events_or_notifications(
    migrated_factory, tmp_config, tmp_path
):
    root, workspace_id = _project(tmp_path)
    clock = _Clock()
    emitter = SqliteEventEmitter(SqliteEventRepo(clock))
    guardrail_service = _service(migrated_factory, emitter=emitter)

    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow, workspace_id)
        _seed_agent(uow, "alpha")
        _seed_agent(uow, "beta")
        _add_guardrail(
            uow,
            guardrail_id="gr_message",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("message",),
            field_targets=("body",),
        )
        _add_guardrail(
            uow,
            guardrail_id="gr_artifact",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("artifact",),
            field_targets=("content",),
        )
        _add_guardrail(
            uow,
            guardrail_id="gr_handoff",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("handoff",),
            field_targets=("payload",),
        )

    messages = MessageService(
        connection_factory=migrated_factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=emitter,
        clock=clock,
        config=tmp_config,
        guardrails=guardrail_service,
    )
    artifacts = ArtifactService(
        connection_factory=migrated_factory,
        artifacts=SqliteArtifactRepo(clock),
        artifact_store=LocalArtifactStore(tmp_config.home_dir / "artifacts"),
        workspaces=SqliteWorkspaceRepo(clock),
        files=WorkspaceFileStore(),
        clock=clock,
        config=tmp_config,
        event_emitter=emitter,
        agents=SqliteAgentRepo(clock),
        guardrails=guardrail_service,
    )
    handoffs = HandoffService(
        connection_factory=migrated_factory,
        handoffs=SqliteHandoffRepo(clock),
        clock=clock,
        config=tmp_config,
        event_emitter=emitter,
        agents=SqliteAgentRepo(clock),
        messages=SqliteMessageRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        guardrails=guardrail_service,
    )

    with pytest.raises(OktoNexusError) as message_denied:
        messages.create_message(
            project_root=root,
            from_agent_id="alpha",
            subject="ok",
            body="contains secret",
        )
    with pytest.raises(OktoNexusError) as artifact_denied:
        artifacts.artifact_put(
            project_root=root,
            artifact_type="text",
            content="contains secret",
            agent_id="alpha",
        )
    with pytest.raises(OktoNexusError) as handoff_denied:
        handoffs.handoff_create(
            project_root=root,
            from_agent_id="alpha",
            target={"strategy": "direct", "agent_id": "beta"},
            visibility="public",
            payload="contains secret",
        )

    assert message_denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert artifact_denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert handoff_denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert _count(migrated_factory, "messages") == 0
    assert _count(migrated_factory, "message_deliveries") == 0
    assert _count(migrated_factory, "artifacts") == 0
    assert _count(migrated_factory, "handoffs") == 0
    assert _event_count(migrated_factory, "message.created") == 0
    assert _event_count(migrated_factory, "artifact.created") == 0
    assert _event_count(migrated_factory, "handoff.created") == 0
    denied_events = _events(migrated_factory)
    assert len(denied_events) == 3
    for payload in denied_events:
        _assert_scrubbed(payload)


def test_guardrail_denies_before_hitl_approval_rows_for_message_and_handoff(
    tmp_path,
):
    env = {
        "OKTO_NEXUS_HOME": str(tmp_path / "home"),
        "OKTO_NEXUS_FEATURE_HITL": "true",
    }
    deps = bootstrap(env, [])
    server = _Server()
    register_tools(server, deps)
    root, _workspace_id = _project(tmp_path)

    assert server.tools["workspace_resolve"](project_root=root)["ok"] is True
    assert (
        server.tools["agent_register"](agent_id="alpha", role="builder")["ok"] is True
    )
    with deps.connection_factory.unit_of_work() as uow:
        _add_guardrail(
            uow,
            guardrail_id="gr_hitl_order",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("message", "handoff"),
            field_targets=("body", "payload"),
        )
        bindings = validate_agent_bindings(
            [
                {
                    "source": "inline",
                    "governance": [
                        {"action": "message_create", "limit_kind": "require_approval"},
                        {"action": "handoff_create", "limit_kind": "require_approval"},
                    ],
                }
            ]
        )
        deps.repos.policy_bindings.replace(uow, agent_id="alpha", bindings=bindings)

    message = server.tools["message_create"](
        project_root=root,
        from_agent_id="alpha",
        subject="ok",
        body="contains secret",
    )
    handoff = server.tools["handoff_create"](
        project_root=root,
        from_agent_id="alpha",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="contains secret",
    )

    assert message["ok"] is False
    assert message["error"]["code"] == ErrorCode.GUARDRAIL_DENIED.value
    assert handoff["ok"] is False
    assert handoff["error"]["code"] == ErrorCode.GUARDRAIL_DENIED.value
    assert _count(deps.connection_factory, "approvals") == 0
    assert _count(deps.connection_factory, "messages") == 0
    assert _count(deps.connection_factory, "handoffs") == 0
    assert _event_count(deps.connection_factory, "approval.requested") == 0
    assert _event_count(deps.connection_factory, "message.created") == 0
    assert _event_count(deps.connection_factory, "handoff.created") == 0
    denied_events = _events(deps.connection_factory)
    assert len(denied_events) == 2
    for payload in denied_events:
        _assert_scrubbed(payload)


def test_guardrail_service_fail_closed_for_unsupported_schema_validation_and_llm(
    migrated_factory,
):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _insert_unvalidated_active_guardrail(
            uow,
            guardrail_id="gr_schema",
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "schema_validation", "schema": {}},
        )
        _insert_unvalidated_active_guardrail(
            uow,
            guardrail_id="gr_llm",
            evaluator_kind=gr.EVALUATOR_KIND_LLM,
            evaluator_config={"provider": "none"},
        )

    svc = _service(migrated_factory)
    with migrated_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError) as denied:
            svc.enforce(
                uow,
                workspace_id="ws_guardrails",
                actor_agent_id="alpha",
                surface="message",
                fields={"body": "benign"},
            )
    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "config_unavailable"
    assert denied.value.details["guardrail_id"] in {"gr_schema", "gr_llm"}


def test_guardrail_service_invalid_regex_config_fails_closed(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _insert_unvalidated_active_guardrail(
            uow,
            guardrail_id="gr_bad_regex",
            evaluator_kind=gr.EVALUATOR_KIND_DETERMINISTIC,
            evaluator_config={"kind": "regex", "patterns": ["["]},
        )

    svc = _service(migrated_factory)
    with migrated_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError) as denied:
            svc.enforce(
                uow,
                workspace_id="ws_guardrails",
                actor_agent_id="alpha",
                surface="message",
                fields={"body": "anything"},
            )
    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "config_unavailable"
    assert denied.value.details["guardrail_id"] == "gr_bad_regex"


def test_guardrail_service_tokenizer_degraded_fails_closed_under_enforce(
    migrated_factory,
):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_tokens",
            evaluator_config={"kind": "token_limit", "max_tokens": 1000},
        )

    svc = _service(migrated_factory, tokenizer=_ApproxTokenizer())
    with pytest.raises(OktoNexusError) as denied:
        with svc.guard(
            workspace_id="ws_guardrails",
            actor_agent_id="alpha",
            surface="message",
            fields={"body": "small text"},
        ):
            pass
    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "config_unavailable"
    assert denied.value.details["guardrail_id"] == "gr_tokens"


def test_guardrail_service_unresolved_actor_fails_closed(migrated_factory):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)

    svc = _service(migrated_factory)
    with pytest.raises(OktoNexusError) as denied:
        with svc.guard(
            workspace_id="ws_guardrails",
            actor_agent_id="ghost",
            surface="message",
            fields={"body": "anything"},
        ):
            pass
    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "config_unavailable"
    assert denied.value.details["guardrail_id"] is None
    events = _events(migrated_factory)
    assert events[0]["actor_agent_id"] == "ghost"
    assert events[0]["reason_code"] == "config_unavailable"


def test_artifact_path_reference_content_guardrail_denies_as_unevaluable(
    migrated_factory, tmp_config, tmp_path
):
    root, workspace_id = _project(tmp_path)
    referenced = tmp_path / "project" / "note.txt"
    referenced.write_text("stored outside inline payload", encoding="utf-8")
    clock = _Clock()
    emitter = SqliteEventEmitter(SqliteEventRepo(clock))
    guardrail_service = _service(migrated_factory, emitter=emitter)

    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow, workspace_id)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_artifact_content",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("artifact",),
            field_targets=("content",),
        )

    artifacts = ArtifactService(
        connection_factory=migrated_factory,
        artifacts=SqliteArtifactRepo(clock),
        artifact_store=LocalArtifactStore(tmp_config.home_dir / "artifacts"),
        workspaces=SqliteWorkspaceRepo(clock),
        files=WorkspaceFileStore(),
        clock=clock,
        config=tmp_config,
        event_emitter=emitter,
        agents=SqliteAgentRepo(clock),
        guardrails=guardrail_service,
    )

    with pytest.raises(OktoNexusError) as denied:
        artifacts.artifact_put(
            project_root=root,
            artifact_type="text",
            path=str(referenced),
            agent_id="alpha",
        )

    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "unevaluable_reference"
    assert denied.value.details["guardrail_id"] == "gr_artifact_content"
    assert _count(migrated_factory, "artifacts") == 0
    assert _event_count(migrated_factory, "artifact.created") == 0
    events = _events(migrated_factory)
    assert len(events) == 1
    assert events[0]["reason_code"] == "unevaluable_reference"
    _assert_scrubbed(events[0], raw_text=str(referenced))


def test_artifact_metadata_target_on_path_reference_evaluates_without_inline_content(
    migrated_factory, tmp_config, tmp_path
):
    root, workspace_id = _project(tmp_path)
    referenced = tmp_path / "project" / "public.txt"
    referenced.write_text("plain file bytes", encoding="utf-8")
    clock = _Clock()
    emitter = SqliteEventEmitter(SqliteEventRepo(clock))
    guardrail_service = _service(migrated_factory, emitter=emitter)

    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow, workspace_id)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_artifact_metadata",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("artifact",),
            field_targets=("metadata.classification",),
        )

    artifacts = ArtifactService(
        connection_factory=migrated_factory,
        artifacts=SqliteArtifactRepo(clock),
        artifact_store=LocalArtifactStore(tmp_config.home_dir / "artifacts"),
        workspaces=SqliteWorkspaceRepo(clock),
        files=WorkspaceFileStore(),
        clock=clock,
        config=tmp_config,
        event_emitter=emitter,
        agents=SqliteAgentRepo(clock),
        guardrails=guardrail_service,
    )

    with pytest.raises(OktoNexusError) as denied:
        artifacts.artifact_put(
            project_root=root,
            artifact_type="text",
            path=str(referenced),
            metadata={"classification": "secret"},
            agent_id="alpha",
        )

    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "keyword_hit"
    assert denied.value.details["guardrail_id"] == "gr_artifact_metadata"
    assert _count(migrated_factory, "artifacts") == 0
    assert _event_count(migrated_factory, "artifact.created") == 0
    events = _events(migrated_factory)
    assert len(events) == 1
    assert events[0]["reason_code"] == "keyword_hit"
    _assert_scrubbed(events[0], raw_text="secret")


def test_message_write_path_unresolved_actor_fails_closed_before_persistence(
    migrated_factory, tmp_config, tmp_path
):
    root, workspace_id = _project(tmp_path)
    clock = _Clock()
    emitter = SqliteEventEmitter(SqliteEventRepo(clock))
    messages = MessageService(
        connection_factory=migrated_factory,
        channels=SqliteChannelRepo(clock),
        messages=SqliteMessageRepo(clock),
        workspaces=SqliteWorkspaceRepo(clock),
        agents=SqliteAgentRepo(clock),
        sessions=SqliteSessionRepo(clock),
        deliveries=SqliteMessageDeliveryRepo(clock),
        event_emitter=emitter,
        clock=clock,
        config=tmp_config,
        guardrails=_service(migrated_factory, emitter=emitter),
    )

    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow, workspace_id)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_any",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            surfaces=("message",),
            field_targets=("body",),
        )

    with pytest.raises(OktoNexusError) as denied:
        messages.create_message(
            project_root=root,
            from_agent_id="ghost",
            subject="ok",
            body="benign",
        )

    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "config_unavailable"
    assert _count(migrated_factory, "messages") == 0
    assert _count(migrated_factory, "message_deliveries") == 0
    assert _event_count(migrated_factory, "message.created") == 0
    events = _events(migrated_factory)
    assert len(events) == 1
    assert events[0]["actor_agent_id"] == "ghost"
    assert events[0]["reason_code"] == "config_unavailable"


def test_guardrail_service_audit_and_warn_matches_do_not_block_or_leak(
    migrated_factory,
):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_warn",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
            mode=gr.ENFORCEMENT_MODE_WARN,
        )

    svc = _service(migrated_factory)
    with migrated_factory.unit_of_work(write=False) as uow:
        result = svc.enforce(
            uow,
            workspace_id="ws_guardrails",
            actor_agent_id="alpha",
            surface="message",
            fields={"body": "contains secret"},
        )
    assert result.denied is False
    assert result.decisions[0].matched is True
    assert result.decisions[0].reason_code == "keyword_hit"
    scrubbed = result.to_scrubbed_dict()
    _assert_scrubbed(scrubbed)
    assert _events(migrated_factory) == []


def test_guardrail_service_broken_audit_emit_never_masks_guardrail_denied(
    migrated_factory,
):
    with migrated_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        _seed_agent(uow, "alpha")
        _add_guardrail(
            uow,
            guardrail_id="gr_keyword",
            evaluator_config={"kind": "keyword_blocklist", "keywords": ["secret"]},
        )

    svc = _service(migrated_factory, emitter=_ExplodingEmitter())
    with pytest.raises(OktoNexusError) as denied:
        with svc.guard(
            workspace_id="ws_guardrails",
            actor_agent_id="alpha",
            surface="message",
            fields={"body": "contains secret"},
        ):
            pass
    assert denied.value.code == ErrorCode.GUARDRAIL_DENIED.value
    assert denied.value.details["reason_code"] == "keyword_hit"
    assert _events(migrated_factory) == []


def test_guardrail_rest_admin_crud_pinned_guard_and_delete_guards(
    guardrail_rest_client,
):
    client, _deps = guardrail_rest_client
    assert client.post("/api/v1/agents", json={"agent_id": "alpha"}).status_code == 200

    group = client.post("/api/v1/guardrails/groups", json={"name": "Reviewers"}).json()[
        "data"
    ]
    gid = group["group_id"]
    member = client.post(
        f"/api/v1/guardrails/groups/{gid}/members", json={"agent_id": "alpha"}
    )
    assert member.status_code == 200

    guardrail = client.post(
        "/api/v1/guardrails",
        json={"name": "Secrets", "description": "block secret terms"},
    ).json()["data"]
    grid = guardrail["guardrail_id"]
    active = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {
                "kind": "keyword_blocklist",
                "keywords": ["secret"],
            },
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert active.status_code == 200
    assert active.json()["data"]["version"] == 1
    draft = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "draft",
            "evaluator_kind": "deterministic",
            "evaluator_config": {
                "kind": "keyword_blocklist",
                "keywords": ["secret"],
            },
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert draft.status_code == 200
    assert draft.json()["data"]["version"] == 2

    invalid_kind = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {"kind": "unsupported"},
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert invalid_kind.status_code == 422
    assert invalid_kind.json()["error"]["code"] == "VALIDATION_ERROR"

    inactive_pin = client.post(
        "/api/v1/guardrails/assignments",
        json={
            "scope_kind": "agent_group",
            "group_id": gid,
            "guardrail_id": grid,
            "version_mode": "pinned",
            "pinned_version": 2,
            "mode": "enforce",
        },
    )
    assert inactive_pin.status_code == 422
    assert inactive_pin.json()["error"]["code"] == "VALIDATION_ERROR"

    assignment = client.post(
        "/api/v1/guardrails/assignments",
        json={
            "scope_kind": "agent_group",
            "group_id": gid,
            "guardrail_id": grid,
            "version_mode": "pinned",
            "pinned_version": 1,
            "mode": "enforce",
        },
    )
    assert assignment.status_code == 200
    assignment_id = assignment.json()["data"]["assignment_id"]

    blocked_group = client.delete(f"/api/v1/guardrails/groups/{gid}")
    assert blocked_group.status_code == 409
    assert blocked_group.json()["error"]["code"] == "CONFLICT"
    assert blocked_group.json()["error"]["details"]["assignments"] == [assignment_id]

    blocked_guardrail = client.delete(f"/api/v1/guardrails/{grid}")
    assert blocked_guardrail.status_code == 409
    assert blocked_guardrail.json()["error"]["code"] == "CONFLICT"
    assert blocked_guardrail.json()["error"]["details"]["assignments"] == [
        assignment_id
    ]

    listed = client.get("/api/v1/guardrails/assignments", params={"agent_id": "alpha"})
    assert [row["assignment_id"] for row in listed.json()["data"]["items"]] == [
        assignment_id
    ]
    assert (
        client.patch(
            f"/api/v1/guardrails/assignments/{assignment_id}",
            json={"mode": "warn", "enabled": False},
        ).json()["data"]["mode"]
        == "warn"
    )

    assert (
        client.delete(f"/api/v1/guardrails/assignments/{assignment_id}").status_code
        == 200
    )
    assert client.delete(f"/api/v1/guardrails/groups/{gid}").status_code == 200
    assert client.delete(f"/api/v1/guardrails/{grid}").status_code == 200


def test_guardrail_rest_validates_rules_and_supports_capability_scope(
    guardrail_rest_client,
):
    client, _deps = guardrail_rest_client
    assert (
        client.post(
            "/api/v1/capabilities",
            json={"name": "review", "description": "Reviews output"},
        ).status_code
        == 200
    )
    guardrail = client.post(
        "/api/v1/guardrails",
        json={"name": "Validated rule"},
    ).json()["data"]
    grid = guardrail["guardrail_id"]

    invalid_regex = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {"kind": "regex", "patterns": ["["]},
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert invalid_regex.status_code == 422
    assert "Invalid regular expression" in invalid_regex.json()["error"]["message"]

    invalid_field = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {
                "kind": "keyword_blocklist",
                "keywords": ["secret"],
            },
            "surfaces": ["artifact"],
            "field_targets": ["body"],
        },
    )
    assert invalid_field.status_code == 422
    assert "unsupported field(s): body" in invalid_field.json()["error"]["message"]

    unsupported_draft = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "draft",
            "evaluator_kind": "deterministic",
            "evaluator_config": {"kind": "schema_validation", "schema": {}},
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert unsupported_draft.status_code == 200
    cannot_activate = client.patch(
        f"/api/v1/guardrails/{grid}/versions/1",
        json={"status": "active"},
    )
    assert cannot_activate.status_code == 422
    assert "runtime evaluator is unavailable" in cannot_activate.json()["error"]["message"]

    active = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {"kind": "regex", "patterns": [r"secret-\d+"]},
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert active.status_code == 200

    assignment = client.post(
        "/api/v1/guardrails/assignments",
        json={
            "scope_kind": "capability",
            "capability": "review",
            "guardrail_id": grid,
        },
    )
    assert assignment.status_code == 200
    assert assignment.json()["data"]["capability"] == "review"
    assert assignment.json()["data"]["mode"] == "audit"

    listed = client.get(
        "/api/v1/guardrails/assignments",
        params={"capability": "review"},
    )
    assert listed.status_code == 200
    assert [item["assignment_id"] for item in listed.json()["data"]["items"]] == [
        assignment.json()["data"]["assignment_id"]
    ]
    blocked_capability = client.delete("/api/v1/capabilities/review")
    assert blocked_capability.status_code == 409
    assert blocked_capability.json()["error"]["details"]["uses"] == [
        {
            "assignment_id": assignment.json()["data"]["assignment_id"],
            "kind": "guardrail_assignment",
        }
    ]


def test_guardrail_versions_are_append_only_across_rest_and_no_mcp_admin_surface(
    guardrail_rest_client, tmp_path
):
    client, _deps = guardrail_rest_client
    guardrail = client.post("/api/v1/guardrails", json={"name": "Append only"}).json()[
        "data"
    ]
    grid = guardrail["guardrail_id"]
    version = client.post(
        f"/api/v1/guardrails/{grid}/versions",
        json={
            "status": "active",
            "evaluator_kind": "deterministic",
            "evaluator_config": {
                "kind": "keyword_blocklist",
                "keywords": ["secret"],
            },
            "surfaces": ["message"],
            "field_targets": ["body"],
        },
    )
    assert version.status_code == 200

    rest_delete = client.delete(f"/api/v1/guardrails/{grid}/versions/1")
    assert rest_delete.status_code == 405

    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = _Server()
    register_tools(server, deps)
    assert "guardrail_version_manage" not in server.tools


def test_guardrail_rest_mutations_are_operator_only(guardrail_rest_client):
    client, deps = guardrail_rest_client
    assert client.post("/api/v1/agents", json={"agent_id": "alpha"}).status_code == 200
    alpha_key = _issue_key(deps, "alpha")
    headers = {"x-api-key": alpha_key}

    calls = [
        ("post", "/api/v1/guardrails/groups", {"name": "Nope"}),
        ("patch", "/api/v1/guardrails/groups/grp_missing", {"name": "Nope"}),
        ("delete", "/api/v1/guardrails/groups/grp_missing", None),
        (
            "post",
            "/api/v1/guardrails/groups/grp_missing/members",
            {"agent_id": "alpha"},
        ),
        ("delete", "/api/v1/guardrails/groups/grp_missing/members/alpha", None),
        ("post", "/api/v1/guardrails", {"name": "Nope"}),
        ("patch", "/api/v1/guardrails/grd_missing", {"name": "Nope"}),
        ("delete", "/api/v1/guardrails/grd_missing", None),
        (
            "post",
            "/api/v1/guardrails/grd_missing/versions",
            {
                "status": "active",
                "evaluator_kind": "deterministic",
                "evaluator_config": {"kind": "keyword_blocklist", "keywords": ["x"]},
                "surfaces": ["message"],
                "field_targets": ["body"],
            },
        ),
        ("patch", "/api/v1/guardrails/grd_missing/versions/1", {"status": "active"}),
        (
            "post",
            "/api/v1/guardrails/assignments",
            {"scope_kind": "global", "guardrail_id": "grd_missing"},
        ),
        ("patch", "/api/v1/guardrails/assignments/gra_missing", {"enabled": False}),
        ("delete", "/api/v1/guardrails/assignments/gra_missing", None),
    ]
    for method, path, body in calls:
        if body is None:
            response = getattr(client, method)(path, headers=headers)
        else:
            response = getattr(client, method)(path, json=body, headers=headers)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    read = client.get("/api/v1/guardrails", headers=headers)
    assert read.status_code == 403
    denials = client.get(
        "/api/v1/guardrails/denials",
        params={"workspace": "ws_guardrails"},
        headers=headers,
    )
    assert denials.status_code == 403


def test_guardrail_denials_rest_read_path_is_scrubbed(guardrail_rest_client):
    client, deps = guardrail_rest_client
    with deps.connection_factory.unit_of_work() as uow:
        _seed_workspace(uow)
        deps.repos.events.append(
            uow,
            workspace_id="ws_guardrails",
            stream="workspace",
            type=GUARDRAIL_DENIED_EVENT,
            actor_agent_id="alpha",
            visibility="public",
            payload={
                "guardrail_id": "gr_1",
                "reason_code": "keyword_hit",
                "body": "raw secret body",
                "nested": {
                    "payload": "raw secret payload",
                    "safe": "metadata only",
                },
            },
        )

    response = client.get(
        "/api/v1/guardrails/denials", params={"workspace": "ws_guardrails"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["s6_behavior"].startswith(
        "audit and warn matches are intentionally silent"
    )
    payload = data["items"][0]["payload"]
    assert payload["guardrail_id"] == "gr_1"
    assert payload["nested"] == {"safe": "metadata only"}
    _assert_scrubbed(data, raw_text="raw secret")


def test_guardrail_mcp_admin_tools_are_not_registered(tmp_path):
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = _Server()
    register_tools(server, deps)

    retired = {
        "guardrail_group_manage",
        "guardrail_manage",
        "guardrail_version_manage",
        "guardrail_assignment_manage",
        "guardrail_denial_list",
    }
    assert retired.isdisjoint(server.tools)
