"""A paused local process retains ownership until release or fenced takeover."""
import os
import socket
import pytest

from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
from okto_nexus.domain.base import iso_plus


def test_same_local_owner_survives_a_pause_longer_than_heartbeat(migrated_factory):
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    resumed = iso_plus(now, 120)
    with migrated_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id='local-owner', now=now,
            lease_expires_at=iso_plus(now, 40), process_pid=os.getpid(), process_host=socket.gethostname())
    with migrated_factory.unit_of_work() as uow:
        assert repo.owns(uow, owner_id='local-owner', epoch=epoch, now=resumed)
        assert repo.heartbeat_owner(uow, owner_id='local-owner', epoch=epoch,
            now=resumed, lease_expires_at=iso_plus(resumed, 40))


def test_released_local_owner_cannot_resume(migrated_factory):
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    with migrated_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id='released-owner', now=now,
            lease_expires_at=iso_plus(now, 40), process_pid=os.getpid(), process_host=socket.gethostname())
        repo.release_owner(uow, owner_id='released-owner', epoch=epoch, now=now)
        assert not repo.owns(uow, owner_id='released-owner', epoch=epoch, now=now)
        assert not repo.heartbeat_owner(uow, owner_id='released-owner', epoch=epoch,
            now=now, lease_expires_at=iso_plus(now, 40))


def test_replaced_epoch_cannot_resume(migrated_factory):
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    with migrated_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id='previous-owner', now=now,
            lease_expires_at=iso_plus(now, 40), process_pid=os.getpid(), process_host=socket.gethostname())
        repo.release_owner(uow, owner_id='previous-owner', epoch=epoch, now=now)
        replacement = repo.acquire_owner(uow, owner_id='replacement', now=now,
            lease_expires_at=iso_plus(now, 40), process_pid=os.getpid(), process_host=socket.gethostname())
        assert replacement > epoch
        assert not repo.owns(uow, owner_id='previous-owner', epoch=epoch, now=now)
        assert not repo.heartbeat_owner(uow, owner_id='previous-owner', epoch=epoch,
            now=now, lease_expires_at=iso_plus(now, 40))


def test_expired_live_local_owner_cannot_be_taken_over(migrated_factory):
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    with migrated_factory.unit_of_work() as uow:
        repo.acquire_owner(uow, owner_id='live', now=now, lease_expires_at=iso_plus(now, 40),
            process_pid=os.getpid(), process_host=socket.gethostname())
        assert repo.acquire_owner(uow, owner_id='competitor', now=iso_plus(now, 120),
            lease_expires_at=iso_plus(now, 160), process_pid=os.getpid(),
            process_host=socket.gethostname()) is None


@pytest.mark.parametrize('identity', ['foreign-host', 'foreign-pid', 'missing'])
def test_expired_owner_without_local_process_identity_cannot_renew(migrated_factory, identity):
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    with migrated_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id='other', now=now, lease_expires_at=iso_plus(now, 40),
            process_pid=None if identity == 'missing' else os.getpid() + (1 if identity == 'foreign-pid' else 0),
            process_host='another-host' if identity == 'foreign-host' else socket.gethostname())
        assert not repo.owns(uow, owner_id='other', epoch=epoch, now=iso_plus(now, 120))
        assert not repo.heartbeat_owner(uow, owner_id='other', epoch=epoch,
            now=iso_plus(now, 120), lease_expires_at=iso_plus(now, 160))


def test_host_contact_commits_with_authority_and_fenced_epoch_cannot_refresh_it(migrated_factory):
    from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
    identity = ensure_execution_installation(migrated_factory)
    repo = SqliteRuntimeOutboxRepo()
    now = '2026-10-07T15:00:00.000000Z'
    resumed = iso_plus(now, 120)
    key = (identity.server_id, identity.embedded_executor_id)
    with migrated_factory.unit_of_work() as uow:
        epoch = repo.acquire_owner(uow, owner_id='local-owner', now=now,
            lease_expires_at=iso_plus(now, 40), process_pid=os.getpid(), process_host=socket.gethostname())
        uow.connection.execute("UPDATE execution_executors SET owner_instance_id='local-owner',"
            "control_state='CONTROL_READY',last_seen_at=? WHERE server_id=? AND executor_id=?", (now, *key))
    with pytest.raises(RuntimeError, match='rollback'):
        with migrated_factory.unit_of_work() as uow:
            assert repo.heartbeat_owner(uow, owner_id='local-owner', epoch=epoch,
                now=resumed, lease_expires_at=iso_plus(resumed, 40))
            raise RuntimeError('rollback')
    with migrated_factory.unit_of_work() as uow:
        def contact():
            return uow.connection.execute('SELECT last_seen_at FROM execution_executors '
                'WHERE server_id=? AND executor_id=?', key).fetchone()[0]
        assert contact() == now
        assert repo.heartbeat_owner(uow, owner_id='local-owner', epoch=epoch,
            now=resumed, lease_expires_at=iso_plus(resumed, 40))
        assert contact() == resumed
        repo.release_owner(uow, owner_id='local-owner', epoch=epoch, now=resumed)
        assert not repo.heartbeat_owner(uow, owner_id='local-owner', epoch=epoch,
            now=iso_plus(resumed, 1), lease_expires_at=iso_plus(resumed, 41))
        assert contact() == resumed
