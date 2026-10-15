"""Only approved equivalent endpoints may receive a proven-unsent operation."""
import json
import time
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_safe_retry import busy_lane
from test_runtime_outbox import wait_status

runtime = runtime_fixture


def fallback_pair(runtime, monkeypatch, group="interchangeable-fixture", *, agent="worker", other_workspace=False,
                  profile_id="profile-pi", open_target=True):
    deps, client, root, _, operator, _ = runtime
    changed = client.patch("/api/v1/harness/endpoints/endpoint-pi", headers={"x-api-key": operator},
        json={"expected_revision": 1, "selection_group": group, "priority": 10})
    assert changed.status_code == 200, changed.text
    first, clock = busy_lane(runtime, monkeypatch)
    if agent != "worker":
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id=agent)
    if other_workspace:
        target_root = Path(root) / "other-workspace"
        target_root.mkdir()
        root = str(target_root)
    if profile_id != "profile-pi":
        created_profile = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json={
            "profile_id": profile_id, "adapter_id": "pi", "enabled": True})
        assert created_profile.status_code == 200, created_profile.text
    created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
        "endpoint_id": "zz-fallback", "agent_id": agent, "adapter_id": "pi", "project_root": root,
        "profile_id": profile_id, "enabled": True, "response_policy": "conversation", "selection_group": group})
    assert created.status_code == 200, created.text
    if open_target:
        opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
            "agent_id": agent, "kind": "pi", "endpoint_id": "zz-fallback", "project_root": root})
        assert opened.status_code == 200, opened.text
    return first, clock
