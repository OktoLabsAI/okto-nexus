"""OBS policy is explicit, bounded and independent of execution settings."""
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.settings import (
    SETTING_SPECS,
    SettingsService,
    detect_pinned_fields,
)
from okto_nexus.config import (
    FEATURE_FLAG_FIELDS,
    NexusConfig,
    OBSERVATION_INTEGER_LIMITS,
    load_config,
)
from okto_nexus.domain.observations import (
    ObservationLimits,
    compute_freshness,
    parse_report,
    report_hash,
)
from okto_nexus.errors import OktoNexusError


DEFAULTS = {
    "feature_observations": False,
    "observation_max_valid_for_seconds": 3600,
    "observation_future_tolerance_seconds": 30,
    "observation_source_stale_seconds": 30,
    "observation_source_rate_per_minute": 60,
    "observation_source_burst": 20,
    "observation_agent_rate_per_minute": 1920,
    "observation_agent_burst": 80,
    "observation_installation_rate_per_minute": 8192,
    "observation_installation_burst": 512,
    "observation_max_sources_per_agent": 32,
    "observation_max_sources": 4096,
    "observation_max_instances": 4096,
    "observation_max_correlation_records": 4096,
    "observation_max_tokens_per_source": 8,
    "observation_event_retention_days": 7,
    "observation_max_events": 20000,
}
NOW = "2026-11-06T15:00:00.000000Z"


@pytest.fixture
def settings(tmp_path):
    config = NexusConfig(home_dir=tmp_path / "home")
    factory = ConnectionFactory(config)
    MigrationRunner(factory).apply()
    service = SettingsService(config, SimpleNamespace(now_iso=lambda: NOW))
    try:
        yield config, factory, service
    finally:
        factory.close()


def test_observation_defaults_are_opt_in_independent_and_protocol_bounds_are_not_settings(tmp_path):
    config = load_config({}, ["--home", str(tmp_path / "home")])
    assert {key: getattr(config, key) for key in DEFAULTS} == DEFAULTS
    assert set(OBSERVATION_INTEGER_LIMITS) == set(DEFAULTS) - {"feature_observations"}
    assert "feature_observations" in FEATURE_FLAG_FIELDS
    specs = {spec.key: spec for spec in SETTING_SPECS}
    for unsupported in ("observation_default_valid_for_seconds", "observation_max_body_bytes",
                        "observation_batch_limit", "observation_token_ttl_seconds",
                        "observation_ingress_queue_size"):
        assert unsupported not in specs
        assert not hasattr(config, unsupported)
    enabled = load_config({"OKTO_NEXUS_FEATURE_OBSERVATIONS": "true"},
                          ["--home", str(tmp_path / "enabled"),
                           "--feature-harness-integrations", "false"])
    assert enabled.feature_observations is True
    assert enabled.feature_harness_integrations is False
    assert enabled.feature_hitl is False
    assert enabled.feature_attention is config.feature_attention


@pytest.mark.parametrize("key", list(OBSERVATION_INTEGER_LIMITS))
def test_every_observation_integer_has_env_cli_precedence_and_hard_bounds(tmp_path, key):
    default, low, high = OBSERVATION_INTEGER_LIMITS[key]
    env_key, flag = "OKTO_NEXUS_" + key.upper(), "--" + key.replace("_", "-")
    home = ["--home", str(tmp_path / "home")]
    assert getattr(load_config({env_key: str(low)}, home), key) == low
    assert getattr(load_config({env_key: str(low)}, [*home, flag, str(high)]), key) == high
    config = load_config({env_key: str(default)}, home)
    assert key in detect_pinned_fields(config)
    for invalid in (str(low - 1), str(high + 1), "true", "1.5"):
        with pytest.raises(OktoNexusError) as error:
            load_config({env_key: invalid}, home)
        assert error.value.code == "CONFIG_ERROR"
        with pytest.raises(OktoNexusError):
            load_config({}, [*home, flag, invalid])


@pytest.mark.parametrize("key", list(OBSERVATION_INTEGER_LIMITS))
@pytest.mark.parametrize("bad", [True, False, 1.0, "1", None])
def test_direct_config_requires_exact_integer_policy_values(tmp_path, key, bad):
    with pytest.raises(OktoNexusError) as error:
        NexusConfig(home_dir=tmp_path / "home", **{key: bad})
    assert error.value.code == "CONFIG_ERROR"


def test_feature_boolean_is_strict_in_programmatic_config(tmp_path):
    for value in (0, 1, "false", None):
        with pytest.raises(OktoNexusError):
            NexusConfig(home_dir=tmp_path / "home", feature_observations=value)
    with pytest.raises(OktoNexusError):
        load_config({"OKTO_NEXUS_FEATURE_OBSERVATIONS": "enabled"})


def test_settings_catalog_exposes_matching_bounds_defaults_and_no_unlimited_switches(settings):
    config, factory, service = settings
    with factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        catalog = {item["key"]: item for item in service.describe(uow)}
        assert uow.connection.total_changes == before
    for key, expected in DEFAULTS.items():
        item = catalog[key]
        assert item["value"] == item["default"] == expected
        assert item["source"] == "default" and item["editable"] is True
        assert item["requires_restart"] is False
        assert item["description"]
        if key != "feature_observations":
            _, low, high = OBSERVATION_INTEGER_LIMITS[key]
            assert (item["min"], item["max"]) == (low, high)
            assert item["group"] == "observations"
            assert low >= (0 if key == "observation_future_tolerance_seconds" else 1)
    assert "explicit smaller TTL" in catalog["observation_max_valid_for_seconds"]["description"]
    assert config.feature_observations is False


def test_settings_patch_validates_entire_observation_policy_before_any_write(settings):
    config, factory, service = settings
    invalid = [(key, bad) for key in OBSERVATION_INTEGER_LIMITS
               for bad in (True, 1.5, "1", None)]
    invalid.extend((key, bound) for key, (_, low, high) in OBSERVATION_INTEGER_LIMITS.items()
                   for bound in (low - 1, high + 1))
    invalid.extend(("feature_observations", value) for value in ("true", 1, None))
    for key, value in invalid:
        # Catch within the writer, then let it commit: validation must prevent
        # even an earlier valid field from being written, not rely on rollback.
        with factory.unit_of_work() as uow:
            before = uow.connection.total_changes
            with pytest.raises(OktoNexusError) as error:
                service.update(uow, {"observation_max_events": 100, key: value})
            assert error.value.code == "CONFIG_ERROR"
            assert uow.connection.total_changes == before
            assert service.load_overrides(uow) == {}
        assert {name: getattr(config, name) for name in DEFAULTS} == DEFAULTS


@pytest.mark.parametrize("commit", [False, True])
def test_observation_patch_becomes_live_only_after_commit_and_persists(settings, commit):
    config, factory, service = settings
    update = {name: low for name, (_, low, _) in OBSERVATION_INTEGER_LIMITS.items()}
    update["feature_observations"] = True
    independent = (config.feature_harness_integrations, config.feature_hitl, config.feature_attention)
    with factory.unit_of_work() as uow:
        service.update(uow, update)
        assert service.load_overrides(uow) == update
        assert {key: getattr(config, key) for key in DEFAULTS} == DEFAULTS
        assert uow.connection.execute("SELECT COUNT(*) FROM server_effective_policy").fetchone()[0] == 0
        if not commit:
            uow.rollback()
    expected = update if commit else DEFAULTS
    assert {key: getattr(config, key) for key in DEFAULTS} == expected
    assert (config.feature_harness_integrations, config.feature_hitl, config.feature_attention) == independent
    restarted = NexusConfig(home_dir=config.home_dir)
    restored = SettingsService(restarted, SimpleNamespace(now_iso=lambda: NOW))
    with factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        restored.apply_overrides(uow)
        assert uow.connection.total_changes == before
    assert {key: getattr(restarted, key) for key in DEFAULTS} == expected


def test_reset_restores_only_observation_defaults_after_commit(settings):
    config, factory, service = settings
    with factory.unit_of_work() as uow:
        service.update(uow, {"feature_observations": True, "observation_max_valid_for_seconds": 20,
                             "attention_unclaimed_seconds": 77})
    with factory.unit_of_work() as uow:
        service.reset(uow, list(DEFAULTS))
        assert config.feature_observations is True
        assert config.observation_max_valid_for_seconds == 20
    assert {key: getattr(config, key) for key in DEFAULTS} == DEFAULTS
    assert config.attention_unclaimed_seconds == 77
    with factory.unit_of_work(write=False) as uow:
        assert service.load_overrides(uow) == {"attention_unclaimed_seconds": 77}


@pytest.mark.parametrize("source", ["env", "cli"])
def test_explicit_default_false_and_limits_remain_pinned_over_persisted_settings(settings, source):
    config, factory, service = settings
    with factory.unit_of_work() as uow:
        service.update(uow, {"feature_observations": True, "observation_max_events": 500})
    env = {"OKTO_NEXUS_FEATURE_OBSERVATIONS": "false", "OKTO_NEXUS_OBSERVATION_MAX_EVENTS": "20000"}
    argv = ["--home", str(config.home_dir)]
    if source == "cli":
        argv.extend(["--feature-observations", "false", "--observation-max-events", "20000"])
        env = {}
    pinned_config = load_config(env, argv)
    pinned = SettingsService(pinned_config, SimpleNamespace(now_iso=lambda: NOW),
                             pinned=detect_pinned_fields(pinned_config))
    with factory.unit_of_work(write=False) as uow:
        pinned.apply_overrides(uow)
        catalog = {item["key"]: item for item in pinned.describe(uow)}
    for key in ("feature_observations", "observation_max_events"):
        assert getattr(pinned_config, key) == DEFAULTS[key]
        assert catalog[key]["source"] == "cli/env" and catalog[key]["editable"] is False
        with factory.unit_of_work() as uow, pytest.raises(OktoNexusError):
            pinned.update(uow, {key: True if key == "feature_observations" else 100})


def test_lower_ttl_policy_does_not_change_protocol_omission_or_replay_hash(settings):
    config, factory, service = settings
    report_data = dict(schema_version=1, source_id="src_one", observed_instance_id="obs_one",
                       generation=1, sequence=1, state="idle", evidence="reported", observed_at=NOW)
    report = parse_report(report_data)
    digest = report_hash(report)
    accepted = compute_freshness(report, received_at=NOW)
    with factory.unit_of_work() as uow:
        service.update(uow, {"observation_max_valid_for_seconds": 20})
    assert config.observation_max_valid_for_seconds == 20
    repeated = parse_report(report_data)
    assert repeated.valid_for_seconds == 90
    assert report_hash(repeated) == digest
    assert accepted.valid_until == "2026-11-06T15:01:30.000000Z"
    # Application checks replay first. New admission uses the current maximum;
    # the limit object's default is irrelevant to this already parsed intent.
    admission = ObservationLimits(default_valid_for_seconds=20, max_valid_for_seconds=20)
    with pytest.raises(OktoNexusError):
        compute_freshness(repeated, received_at=NOW, limits=admission)
    explicit = parse_report(dict(report_data, valid_for_seconds=20))
    assert compute_freshness(explicit, received_at=NOW, limits=admission).valid_until == "2026-11-06T15:00:20.000000Z"


def test_old_default_setting_is_not_an_unimplemented_mutable_policy(settings):
    _, factory, service = settings
    with factory.unit_of_work() as uow, pytest.raises(OktoNexusError) as error:
        service.update(uow, {"observation_default_valid_for_seconds": 30})
    assert error.value.code == "CONFIG_ERROR"
