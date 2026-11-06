"""Committed settings become live in writer order, never during a transaction."""
import threading
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.application.settings import SettingsService
from okto_nexus.config import NexusConfig
from okto_nexus.errors import OktoNexusError


@pytest.fixture
def settings(tmp_path):
    config = NexusConfig(home_dir=tmp_path / 'home')
    factory = ConnectionFactory(config)
    MigrationRunner(factory).apply()
    service = SettingsService(config, SimpleNamespace(now_iso=lambda: '2026-11-06T12:00:00Z'))
    yield config, factory, service
    factory.close()


@pytest.mark.parametrize('commit', [True, False])
@pytest.mark.parametrize('action', ['update', 'reset'])
def test_live_value_waits_for_commit(settings, commit, action):
    config, factory, service = settings
    if action == 'reset':
        with factory.unit_of_work() as uow:
            service.update(uow, {'feature_hitl': True})
    original = config.feature_hitl
    with factory.unit_of_work() as uow:
        if action == 'update':
            service.update(uow, {'feature_hitl': not original})
        else:
            service.reset(uow, ['feature_hitl'])
        assert config.feature_hitl is original
        if not commit:
            uow.rollback()
    assert config.feature_hitl is (not original if commit else original)


def test_reset_validates_entire_request_before_deleting(settings):
    config, factory, service = settings
    with factory.unit_of_work() as uow:
        service.update(uow, {'feature_hitl': True})
    with factory.unit_of_work() as uow:
        with pytest.raises(OktoNexusError):
            service.reset(uow, ['feature_hitl', 'not-a-setting'])
        assert service.load_overrides(uow) == {'feature_hitl': True}
    assert config.feature_hitl is True


def test_concurrent_settings_writers_apply_cache_in_commit_order(settings):
    config, factory, service = settings
    committed = threading.Event()
    release_cache = threading.Event()
    second_queued = threading.Event()
    errors = []

    def pause_cache():
        committed.set()
        assert release_cache.wait(5)

    def first():
        try:
            with factory.unit_of_work() as uow:
                # Delay the first cache application after its real SQLite COMMIT.
                uow.after_commit(pause_cache)
                service.update(uow, {'feature_hitl': True})
        except BaseException as exc:
            errors.append(exc)

    def second():
        try:
            second_queued.set()
            with factory.unit_of_work() as uow:
                assert config.feature_hitl is True
                service.update(uow, {'feature_hitl': False})
        except BaseException as exc:
            errors.append(exc)

    one = threading.Thread(target=first)
    two = threading.Thread(target=second)
    one.start()
    try:
        assert committed.wait(5)
        assert config.feature_hitl is False
        with factory.unit_of_work(write=False) as uow:
            assert service.load_overrides(uow) == {'feature_hitl': True}
        two.start()
        assert second_queued.wait(5)
    finally:
        release_cache.set()
        one.join(5)
        if two.ident is not None:
            two.join(5)
    assert not one.is_alive() and not two.is_alive()
    assert errors == []
    assert config.feature_hitl is False
    with factory.unit_of_work(write=False) as uow:
        assert service.load_overrides(uow) == {'feature_hitl': False}
