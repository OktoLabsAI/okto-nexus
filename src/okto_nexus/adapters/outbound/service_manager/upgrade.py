"""Upgrade effects scoped to the selected Server home and database."""
from contextlib import contextmanager, ExitStack

from ....service_upgrade import ServiceUpgrade, UpgradeHost, fail
from .context import CONTEXT_NAME, atomic_json, read_json, document_revision, validate_context
from .identity import windows_logon_session
from .installation import INSTALLATION_NAME, CONTROL_NAME
from .inspection import inspect_local_server
from .local import LAUNCH_NAME, launch_exclusion
from .locking import ExclusiveFileLock, LockBusy


class ServerUpgradeHost(UpgradeHost):
    component = 'server'
    read, write, digest = staticmethod(read_json), staticmethod(atomic_json), staticmethod(document_revision)
    logon_session = staticmethod(windows_logon_session)

    def __init__(self, lifecycle):
        self.lifecycle = lifecycle
        self.home, self.database = lifecycle.home, lifecycle.database
        self.installation = lifecycle.installation
        self.instance_id = self.installation.instance_id
        self.context_path = self.home / CONTEXT_NAME
        self.installation_path = self.home / INSTALLATION_NAME
        self.control_path = self.home / CONTROL_NAME
        self.launch_path = self.home / LAUNCH_NAME
        self.run_path = self.home / 'service-run.json'
        self.completed_path = self.home / 'service-upgrade.json'
        self.shutdown_path = self.home / 'service-shutdown.json'

    def validate(self, context, *, require_paths=True):
        validate_context(context, require_paths=require_paths)
        from pathlib import Path
        for flag, expected in (('--home', self.home), ('--db-path', self.database)):
            arguments = context['arguments']
            if arguments.count(flag) != 1 or arguments.index(flag) + 1 >= len(arguments):
                fail('UPGRADE_INSTANCE_MISMATCH', 'The context must explicitly select one home and database.')
            if Path(arguments[arguments.index(flag) + 1]).resolve() != expected:
                fail('UPGRADE_INSTANCE_MISMATCH', 'The context selects a different home or database.')
        return context

    def status(self):
        return inspect_local_server(home=self.home, database=self.database,
            host=self.lifecycle.host, port=self.lifecycle.port)

    def runtime_exists(self):
        return self.database.exists() or self.run_path.exists()

    def claim_snapshot(self, receipt):
        return self.optional(self.installation.database_claim) or None

    def _new_claim(self, confirmed):
        return None if not confirmed else {'revision': 1, 'instance_id': self.instance_id,
            'home': str(self.home), 'token': confirmed['token']}

    def check_claim(self, body, confirmed, *, committed=False):
        actual = self.claim_snapshot(None)
        allowed = (self._new_claim(confirmed),) if committed else (
            (body.get('source_claim'), self._new_claim(confirmed)) if confirmed else (body.get('source_claim'),))
        if actual not in allowed:
            fail('UPGRADE_DATABASE_CLAIM_CONFLICT', 'A different supervisor claims this database; its receipt was preserved.')

    def publish_claim(self, body, confirmed):
        self.check_claim(body, confirmed)
        self.write(self.installation.database_claim, self._new_claim(confirmed))

    @contextmanager
    def exclusion(self):
        try:
            with launch_exclusion(self.home, self.database), ExitStack() as owners:
                if self.status()['state'] != 'stopped':
                    fail('UPGRADE_OWNER_UNCONFIRMED', 'Drain the source owner before applying; no process was stopped.')
                for path in sorted({self.home / 'nexus.serve.guard',
                        self.database.with_name(self.database.name + '.serve.guard')}):
                    lock = ExclusiveFileLock(path)
                    lock.acquire()
                    owners.callback(lock.release)
                yield
        except LockBusy:
            fail('UPGRADE_OWNER_UNCONFIRMED', 'Another owner or lifecycle operation holds this home or database.')


def for_lifecycle(lifecycle):
    return ServiceUpgrade(ServerUpgradeHost(lifecycle))
