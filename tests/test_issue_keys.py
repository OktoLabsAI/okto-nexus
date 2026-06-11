"""`okto-nexus admin issue-keys` (spec S1, C8 / FR7 / TS8)."""

from __future__ import annotations

import io
import json

from okto_nexus.adapters.inbound.cli.admin import run_admin
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.domain.keys import hash_api_key, is_well_formed_api_key


def _deps_factory(deps):
    def factory(env, extra):
        return deps

    return factory


def test_issue_keys_is_additive_and_idempotent(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="v1-alpha")
        deps.repos.agents.upsert(uow, agent_id="v1-bravo")
        deps.repos.agents.upsert(uow, agent_id="keyed")
        pre_existing = deps.repos.agents
        pre_existing.set_key_hash(
            uow, agent_id="keyed", api_key_hash="f" * 64
        )

    out = io.StringIO()
    code = run_admin(
        ["issue-keys", "--project-root", str(tmp_path)],
        env={},
        out=out,
        deps_factory=_deps_factory(deps),
    )
    assert code == 0
    report = json.loads(out.getvalue())
    assert report["issued"] == 2
    assert set(report["keys"]) == {"v1-alpha", "v1-bravo"}
    for plaintext in report["keys"].values():
        assert is_well_formed_api_key(plaintext)

    with deps.connection_factory.unit_of_work() as uow:
        # Issued agents now hold the matching hash; the keyed one is untouched.
        for agent_id, plaintext in report["keys"].items():
            agent = deps.repos.agents.get(uow, agent_id)
            assert agent.api_key_hash == hash_api_key(plaintext)
        keyed = deps.repos.agents.get(uow, "keyed")
        assert keyed.api_key_hash == "f" * 64  # never rotated (br_3d1b211e)

    # Second run: informative no-op.
    out2 = io.StringIO()
    code = run_admin(
        ["issue-keys", "--project-root", str(tmp_path)],
        env={},
        out=out2,
        deps_factory=_deps_factory(deps),
    )
    assert code == 0
    assert json.loads(out2.getvalue())["issued"] == 0
