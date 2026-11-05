"""Lifecycle orchestration. Runtime authority remains in existing gates."""
from __future__ import annotations

from ..domain.service_lifecycle import ServiceReadiness


class ServiceLifecycle:
    """One orchestration path for CLI/onboarding; adapters own OS/transport I/O."""
    def __init__(self, adapter, *, monotonic, sleep):
        self.adapter, self.monotonic, self.sleep = adapter, monotonic, sleep

    def inspect(self, *, timeout=2.0):
        return self.adapter.inspect(timeout=timeout)

    def recover_start(self, *, expected_revision):
        return self.adapter.recover_start(expected_revision=expected_revision)

    def upgrade_plan(self, *, executable):
        return self.adapter.upgrade_plan(executable=executable)

    def upgrade_apply(self, *, document, expected_revision):
        return self.adapter.upgrade_apply(document=document, expected_revision=expected_revision)

    def logs(self, *, tail=50, follow=False):
        cursor = None
        while True:
            result, cursor = self.adapter.logs(tail=tail, cursor=cursor)
            yield result
            if not follow or result['state'] == 'unavailable':
                return
            self.sleep(.5)

    def start(self, *, timeout=30.0):
        return self.ensure_running(timeout=timeout)

    def ensure_running(self, *, timeout=30.0):
        deadline = self.monotonic() + timeout
        result = self.adapter.start()
        while result['state'] in {'starting', 'degraded', 'unknown'}:
            if result.get('reason') not in {'STARTUP_PENDING', 'CONCURRENT_START',
                    'SERVICE_UNREACHABLE', 'INSTANCE_OWNERSHIP_UNCONFIRMED',
                    'INSTANCE_METADATA_UNAVAILABLE', 'SUPERVISOR_PENDING'}:
                return result
            # A concurrent publisher/Windows file-sharing window can prevent
            # reading owner metadata. Re-inspect within this deadline; never
            # call start again or infer absence from an unreadable record.
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return {**result, 'wait_timed_out': True,
                    'next_action': 'Query status again. This timeout did not stop or restart the service.'}
            self.sleep(min(.1, remaining))
            result = self.adapter.inspect(timeout=min(1.0, max(.01, deadline - self.monotonic())))
        return result

    def stop(self, *, timeout=30.0):
        deadline = self.monotonic() + timeout
        before = self.adapter.inspect(timeout=min(2, timeout))
        if before['state'] == 'stopped':
            return before
        pending = before.get('reason') == 'SUPERVISOR_PENDING' and not before.get('generation')
        if before['state'] not in {'ready', 'stopping'} and not pending:
            return before
        generation = before.get('generation')
        if not generation and not pending:
            return before
        result = self.adapter.request_stop(before, timeout=max(.01, deadline - self.monotonic()))
        if result['state'] not in {'ready', 'stopping'} or result.get('reason') == 'CONCURRENT_LIFECYCLE':
            return result
        report = result.get('shutdown', {'state': 'UNCONFIRMED'})
        while True:
            remaining = deadline - self.monotonic()
            observed = self.adapter.inspect(timeout=min(1, max(.01, remaining)))
            if observed['state'] == 'stopped':
                drained = report['state'] == 'DRAINED' or self.adapter.shutdown_receipt(generation) == 'DRAINED'
                return {**observed, 'shutdown_outcome': 'drained' if drained else 'unconfirmed',
                    'reason': 'SHUTDOWN_COMPLETE' if drained else 'SHUTDOWN_OUTCOME_UNCONFIRMED',
                    'next_action': None if drained else 'Inspect retained runtime recovery state before resuming work.'}
            if observed.get('generation') not in {None, generation}:
                return {**observed, 'state': 'failed', 'reason': 'INSTANCE_CHANGED',
                    'next_action': 'The observed generation changed; no further shutdown was requested.'}
            if remaining <= 0:
                return {**observed, 'shutdown': report, 'wait_timed_out': True,
                    'next_action': 'Drain remains in progress or unconfirmed. Inspect status; no force was requested.'}
            self.sleep(min(.1, remaining))

    def restart(self, *, timeout=30.0):
        stopped = self.stop(timeout=timeout)
        if stopped['state'] != 'stopped' or stopped.get('shutdown_outcome') == 'unconfirmed':
            return stopped
        return self.start(timeout=timeout)

    def install_user_service(self, *, timeout=30.0):
        prepared = self.adapter.prepare_install()
        if not prepared.get('installation_prepared') or prepared.get('installation_state') == 'installed':
            return prepared
        stopped = self.stop(timeout=timeout)
        if stopped['state'] != 'stopped' or stopped.get('shutdown_outcome') == 'unconfirmed':
            return stopped
        return self.adapter.install_user_service()

    def uninstall_user_service(self, *, timeout=30.0):
        # A retained receipt with a missing native task can be removed only
        # after the adapter independently verifies there is no process owner.
        before = self.inspect(timeout=min(timeout, 2))
        if before.get('reason') in {'SERVICE_DEFINITION_MISSING', 'INSTALLATION_PENDING'}:
            return self.adapter.uninstall_user_service()
        stopped = self.stop(timeout=timeout)
        if stopped['state'] != 'stopped' or stopped.get('shutdown_outcome') == 'unconfirmed':
            return stopped
        return self.adapter.uninstall_user_service()

    def enable_user_service(self, *, timeout=30.0):
        return self.adapter.set_user_service_enabled(True)

    def disable_user_service(self, *, timeout=30.0):
        return self.adapter.set_user_service_enabled(False)


def project_server_readiness(*, identity: str, generation: str, version: str,
                             pid: int, owns_instance: bool, startup_complete: bool,
                             admission_closed: bool, shutdown_state: str,
                             supervisor: str = 'foreground') -> ServiceReadiness:
    if not owns_instance:
        state, reason, action = 'failed', 'INSTANCE_OWNERSHIP_LOST', 'Inspect the configured instance before starting work.'
    elif shutdown_state != 'RUNNING' or admission_closed:
        state, reason, action = 'stopping', 'RUNTIME_DRAINING', 'Observe the current shutdown; do not start a second instance.'
    elif not startup_complete:
        state, reason, action = 'starting', 'STARTUP_INCOMPLETE', 'Wait for initialization of this same generation.'
    else:
        state, reason, action = 'ready', None, None
    return ServiceReadiness(
        component='server', instance_id=identity, generation=generation,
        active_version=version, pid=pid, supervisor=supervisor, state=state,
        ready_for_queries=owns_instance and startup_complete,
        storage_initialized=startup_complete,
        admission='closed' if not owns_instance or admission_closed or shutdown_state != 'RUNNING' else 'canonical_scope_checks_required',
        reason=reason, next_action=action,
    )
