"""OBS grants are explicit; adding the catalog never grants legacy identities access."""
from copy import deepcopy

import pytest

from okto_nexus.domain.permissions import (
    BUILTIN_PRESETS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_REGISTRY,
    PermissionSet,
    builtin_preset,
    validate_permission_flags,
)
from okto_nexus.errors import ErrorCode, OktoNexusError
from test_permissions import loopback_client  # noqa: F401


def test_observation_catalog_is_explicit_and_all_old_defaults_are_preserved():
    assert PERMISSION_REGISTRY["observations"] == {"manage_self": False, "publish": False}
    for flag in PERMISSION_REGISTRY["observations"]:
        assert PERMISSION_DESCRIPTIONS[f"observations.{flag}"]
    for group, entries in PERMISSION_REGISTRY.items():
        if group == "observations":
            continue
        for flag, default in entries.items():
            if isinstance(default, bool):
                assert default is True
                assert PermissionSet(None).allows(group, flag)
                assert PermissionSet({group: {flag: False}}).allows(group, flag) is False
            else:
                assert default == 0
                assert PermissionSet(None).limit(flag) == 0


@pytest.mark.parametrize("flags", [None, {}, {"messages": {"send_direct": True}},
    {"observations": {}}, {"observations": None}, {"observations": []},
    {"observations": "true"}, {"observations": True}, ["observations"], "observations"])
def test_missing_or_malformed_observation_group_never_grants_access(flags):
    permissions = PermissionSet(flags)
    assert permissions.allows("observations", "manage_self") is False
    assert permissions.allows("observations", "publish") is False


@pytest.mark.parametrize("value", [None, False, 0, 1, "true", "false", [], {}, [True]])
def test_only_boolean_true_grants_an_observation_flag(value):
    for flag in ("manage_self", "publish"):
        permissions = PermissionSet({"observations": {flag: value}})
        assert permissions.allows("observations", flag) is False
        with pytest.raises(OktoNexusError) as error:
            permissions.require("observations", flag)
        assert error.value.code == ErrorCode.PERMISSION_DENIED
        assert error.value.details == {"required_permission": f"observations.{flag}"}


def test_observation_grants_are_independent_and_revocable():
    for flag, other in (("manage_self", "publish"), ("publish", "manage_self")):
        granted = validate_permission_flags({"observations": {flag: True}})
        assert PermissionSet(granted).allows("observations", flag)
        assert not PermissionSet(granted).allows("observations", other)
        granted["observations"][flag] = False
        assert not PermissionSet(granted).allows("observations", flag)
    for invalid in (None, 1, "true"):
        with pytest.raises(OktoNexusError):
            validate_permission_flags({"observations": {"publish": invalid}})


def test_builtin_and_legacy_custom_presets_do_not_acquire_observation_grants():
    for original in BUILTIN_PRESETS:
        current = builtin_preset(original["preset_id"])
        assert current["flags"]["observations"] == {"manage_self": False, "publish": False}
        legacy = deepcopy(current["flags"])
        del legacy["observations"]
        copied = validate_permission_flags(legacy)
        assert copied == legacy
        assert "observations" not in copied
        for flags in (current["flags"], copied):
            assert not PermissionSet(flags).allows("observations", "manage_self")
            assert not PermissionSet(flags).allows("observations", "publish")
        current["flags"]["observations"]["publish"] = True
        assert original["flags"]["observations"]["publish"] is False


def test_existing_operator_editor_can_explicitly_grant_revoke_and_reset_observations(loopback_client):  # noqa: F811
    deps, client = loopback_client
    created = client.post("/api/v1/agents", json={"agent_id": "observation-owner"})
    assert created.status_code == 200
    def resolved():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return PermissionSet(deps.repos.agents.get(uow, "observation-owner").permissions)

    assert not resolved().allows("observations", "publish")
    for flags in ({"manage_self": True, "publish": True}, {"manage_self": True, "publish": False}):
        patched = client.patch("/api/v1/agents/observation-owner", json={"permissions": {"observations": flags}})
        assert patched.status_code == 200
        for flag, expected in flags.items():
            assert resolved().allows("observations", flag) is expected
    reset = client.patch("/api/v1/agents/observation-owner", json={"permissions": None})
    assert reset.status_code == 200
    assert not resolved().allows("observations", "manage_self")
    assert not resolved().allows("observations", "publish")
    assert resolved().allows("messages", "send_direct")
