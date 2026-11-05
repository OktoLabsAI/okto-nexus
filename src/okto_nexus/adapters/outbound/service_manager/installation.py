"""Instance-scoped user-task registration and durable host ownership receipts.

All mutations are called under the host's home AND database launch exclusion.
This adapter does not drain, spawn, signal, delete user data or adopt foreign
tasks. Native calls are deliberately injectable for disposable isolated tests.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets

from nexus_connector_core.user_service_definition import (
    UserServiceDefinition, windows_logon_task, windows_definition_digest, windows_enablement_matches)

from .context import CONTEXT_NAME, atomic_json, read_json, validate_context
from .identity import effective_principal, server_instance_id, windows_logon_session
from .windows_tasks import TaskConflict, WindowsTasks

INSTALLATION_NAME = 'service-installation.json'
CONTROL_NAME = 'service-control.json'
SUPERVISOR = 'windows-task-scheduler'


def context_digest(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


class InstallationError(ValueError):
    def __init__(self, code, action):
        super().__init__(code)
        self.code, self.action = code, action


class ServerInstallation:
    def __init__(self, home, database, *, tasks=None):
        self.home, self.database = Path(home).resolve(), Path(database).resolve()
        self.tasks = tasks if tasks is not None else WindowsTasks()
        self.instance_id = server_instance_id(self.home, self.database)
        self.name = f'OktoNexus-server-{self.instance_id[4:]}'
        self.path = self.home / INSTALLATION_NAME
        self.database_claim = self.database.with_name(self.database.name + '.service-installation.json')

    def _claim(self, receipt=None, *, required=False):
        try:
            claim = read_json(self.database_claim)
        except FileNotFoundError:
            if required:
                raise InstallationError('SERVICE_DATABASE_CLAIM_MISSING', 'Restore or reconcile this installation ownership receipt before starting.')
            return
        except (OSError, ValueError) as error:
            raise InstallationError('SERVICE_DATABASE_CLAIM_UNAVAILABLE', 'Inspect the retained database service ownership receipt.') from error
        if (not receipt or claim.get('instance_id') != self.instance_id
                or claim.get('token') != receipt['token'] or claim.get('home') != str(self.home)):
            raise InstallationError('SERVICE_DATABASE_CLAIM_CONFLICT',
                'This database has a different or unconfirmed installed supervisor. Reconcile that installation before starting another instance.')

    def _platform(self):
        if os.name != 'nt':
            raise InstallationError('USER_SERVICE_PLATFORM_UNQUALIFIED',
                'This installer currently targets Windows logon tasks. Keep the existing foreground supervisor on this platform.')

    def receipt(self):
        try:
            value = read_json(self.path)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise InstallationError('INSTALLATION_RECEIPT_UNAVAILABLE',
                'Inspect the selected instance installation receipt before changing its supervisor.') from error
        if (value.get('revision') != 1 or value.get('instance_id') != self.instance_id
                or value.get('principal') != effective_principal() or value.get('name') != self.name
                or value.get('supervisor') != SUPERVISOR
                or value.get('state') not in {'installing', 'installed', 'removing'}
                or not isinstance(value.get('token'), str) or len(value['token']) != 32):
            raise InstallationError('INSTALLATION_RECEIPT_INVALID',
                'Reconcile the retained receipt with the selected user and instance; no task was changed.')
        return value

    def observe(self, *, check_context=True):
        self._platform()
        receipt = self.receipt()
        self._claim(receipt, required=receipt is not None)
        task = self.tasks.read(self.name)
        if receipt is None:
            if task is not None:
                raise InstallationError('FOREIGN_SERVICE_DEFINITION',
                    'A task exists without this instance ownership receipt. Review it in Task Scheduler; it was preserved.')
            return None, None
        if receipt['state'] != 'installed':
            raise InstallationError('INSTALLATION_PENDING',
                'Repeat install or uninstall to reconcile the retained operation. An unconfirmed existing task is never adopted automatically.')
        if task is None:
            raise InstallationError('SERVICE_DEFINITION_MISSING',
                'The installed task is missing. Repeat uninstall to clear its receipt, then install explicitly.')
        if receipt.get('enablement') is not None:
            raise InstallationError('SERVICE_ENABLEMENT_PENDING',
                'Repeat the same enable/disable operation to confirm its retained intent before another lifecycle change.')
        if task.digest != receipt.get('native_digest'):
            raise InstallationError('SERVICE_DEFINITION_CHANGED',
                'Review the edited task in Task Scheduler and restore the recorded definition before retrying. No overwrite was attempted.')
        if check_context:
            self._check_context(receipt)
        return receipt, task

    def _check_context(self, receipt):
        try:
            context = validate_context(read_json(self.home / CONTEXT_NAME))
        except (OSError, ValueError) as error:
            raise InstallationError('SERVICE_CONTEXT_UNAVAILABLE',
                'Restore the recorded interpreter, working directory and service context before starting.') from error
        if context_digest(context) != receipt.get('context_digest'):
            raise InstallationError('SERVICE_CONTEXT_CHANGED',
                'The execution context changed. Reconcile it explicitly before starting the installed task.')

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Enablement must be boolean')
        self._platform()
        receipt = self.receipt()
        self._claim(receipt, required=receipt is not None)
        if receipt is None:
            self.observe()
            raise InstallationError('USER_SERVICE_NOT_INSTALLED', 'Install the selected user integration before changing enablement.')
        if receipt['state'] != 'installed':
            raise InstallationError('INSTALLATION_PENDING', 'Complete the pending installation/removal before changing enablement.')
        task = self.tasks.read(self.name)
        if task is None:
            raise InstallationError('SERVICE_DEFINITION_MISSING', 'Reconcile the missing installed task before changing enablement.')
        pending = receipt.get('enablement')
        if pending is not None:
            if (not isinstance(pending, dict) or type(pending.get('target')) is not bool
                    or pending.get('from_digest') != receipt.get('native_digest')):
                raise InstallationError('INSTALLATION_RECEIPT_INVALID', 'Inspect the retained enablement intent; no task was changed.')
            if pending['target'] != enabled:
                raise InstallationError('SERVICE_ENABLEMENT_PENDING', 'Complete the retained enable/disable operation before requesting the opposite transition.')
        else:
            receipt, task = self.observe(check_context=enabled)
            if task.enabled == enabled:
                return {'enabled': enabled, 'changed': False, 'definition_digest': task.digest}
        if enabled:
            self._check_context(receipt)
        if windows_definition_digest(receipt.get('native_xml')) != receipt.get('native_digest'):
            raise InstallationError('INSTALLATION_RECEIPT_INVALID', 'The retained native export does not match its fingerprint.')
        if pending is None:
            receipt = {**receipt, 'enablement': {'target': enabled, 'from_digest': receipt['native_digest']}}
            atomic_json(self.path, receipt)  # intent precedes the native mutation
        if task.digest == receipt['native_digest']:
            self.tasks.set_enabled(self.name, receipt['native_digest'], enabled)
            task = self.tasks.read(self.name)
        if (task is None or task.enabled != enabled
                or not windows_enablement_matches(receipt['native_xml'], task.xml, enabled)):
            raise InstallationError('SERVICE_ENABLEMENT_UNCONFIRMED', 'The observed task is not the retained enablement-only result. Review it; no overwrite or fallback was attempted.')
        confirmed = {**receipt, 'native_digest': task.digest, 'native_xml': task.xml}
        confirmed.pop('enablement', None)
        atomic_json(self.path, confirmed)
        return {'enabled': enabled, 'changed': True, 'definition_digest': task.digest}

    def prepare(self, context):
        """Read-only preflight before the application is asked to drain."""
        self._platform()
        context = validate_context(context)
        receipt = self.receipt()
        self._claim(receipt)
        task = self.tasks.read(self.name)
        if receipt is None and task is not None:
            raise InstallationError('FOREIGN_SERVICE_DEFINITION', 'The existing task has no matching receipt; it was preserved.')
        if receipt is not None:
            if context_digest(context) != receipt.get('context_digest'):
                raise InstallationError('SERVICE_CONTEXT_CHANGED', 'Uninstall the existing integration before selecting another execution context.')
            if receipt['state'] == 'installing' and task is None:
                return context  # positive absence; same CREATE can be retried
            if (receipt['state'] == 'installing' and task is not None
                    and task.digest == receipt.get('native_digest')):
                return context  # the successful native response was persisted
            self.observe()
        executable = Path(context['executable'])
        if executable.name.lower() == 'python.exe':
            executable = executable.with_name('pythonw.exe')
        if not executable.is_file():
            raise InstallationError('SERVICE_EXECUTABLE_MISSING', 'Install a complete Python environment with pythonw.exe before registering a consoleless task.')
        self.tasks.validate(self.name, windows_logon_task(self.definition(context, '0' * 32)))
        return context

    def definition(self, context, token):
        executable = Path(context['executable'])
        if executable.name.lower() == 'python.exe':
            executable = executable.with_name('pythonw.exe')
        return UserServiceDefinition('server', self.instance_id, effective_principal(),
            str(executable), ('-I', '-m', 'okto_nexus.adapters.inbound.cli.supervised_service',
            str(self.home), str(self.database), token), context['cwd'])

    def install(self, context):
        context = self.prepare(context)
        receipt = self.receipt()
        if receipt is not None and receipt['state'] == 'installed':
            return receipt
        if receipt is not None and receipt.get('native_digest'):
            task = self.tasks.read(self.name)
            if task is not None and task.digest == receipt['native_digest']:
                atomic_json(self.database_claim, {'revision': 1, 'instance_id': self.instance_id,
                    'home': str(self.home), 'token': receipt['token']})
                receipt = {**receipt, 'state': 'installed'}
                atomic_json(self.path, receipt)
                return receipt
        token = receipt['token'] if receipt else secrets.token_hex(16)
        definition = self.definition(context, token)
        xml = windows_logon_task(definition)
        receipt = {'revision': 1, 'component': 'server', 'instance_id': self.instance_id,
            'principal': definition.principal, 'name': self.name, 'supervisor': SUPERVISOR,
            'token': token, 'state': 'installing', 'definition_revision': 1,
            'definition_digest': definition.revision_digest, 'context_digest': context_digest(context)}
        atomic_json(self.home / CONTEXT_NAME, context)
        atomic_json(self.path, receipt)  # precedes the OS effect; retained on error
        atomic_json(self.database_claim, {'revision': 1, 'instance_id': self.instance_id,
            'home': str(self.home), 'token': token})
        atomic_json(self.home / CONTROL_NAME, {'revision': 1, 'token': token, 'desired': 'running'})
        registered = self.tasks.create(self.name, xml)
        receipt = {**receipt, 'native_digest': registered.digest, 'native_xml': registered.xml}
        atomic_json(self.path, receipt)
        task = self.tasks.read(self.name)
        if task is None or task.digest != registered.digest:
            raise InstallationError('INSTALLATION_UNCONFIRMED', 'The task registration could not be observed; inspect the retained installation receipt.')
        # Persist the OS export, not a fingerprint of the unnormalized template.
        receipt = {**receipt, 'state': 'installed', 'native_digest': task.digest}
        atomic_json(self.path, receipt)
        return receipt

    def control(self, receipt):
        try:
            control = read_json(self.home / CONTROL_NAME)
        except (OSError, ValueError) as error:
            raise InstallationError('SERVICE_CONTROL_UNAVAILABLE', 'Inspect the retained lifecycle control receipt before starting.') from error
        if control.get('token') != receipt['token'] or control.get('desired') not in {'running', 'draining'}:
            raise InstallationError('SERVICE_CONTROL_INVALID', 'Reconcile the lifecycle control receipt with this installation.')
        return control

    def start(self):
        receipt, task = self.observe()
        if receipt is None:
            return False
        if not task.enabled:
            raise InstallationError('SERVICE_DISABLED', 'Use service enable --user for this instance before starting it.')
        if task.active:
            return True
        control = self.control(receipt)
        if control.get('launch_requested'):
            return True  # response loss/queued start is observed, never resubmitted
        if task.state == 0:
            raise InstallationError('SUPERVISOR_STATE_UNCONFIRMED', 'Inspect this task in Task Scheduler; no second launch was requested.')
        atomic_json(self.home / CONTROL_NAME, {'revision': 1, 'token': receipt['token'],
            'desired': 'running', 'launch_requested': True})
        self.tasks.start(self.name, receipt['native_digest'])
        return True

    def begin_stop(self, generation):
        receipt, _ = self.observe()
        if receipt is not None:
            control = self.control(receipt)
            atomic_json(self.home / CONTROL_NAME, {'revision': 1, 'token': receipt['token'],
                'desired': 'draining', 'generation': generation,
                'logon_session': control.get('logon_session') or windows_logon_session()})

    def uninstall(self):
        self._platform()
        receipt = self.receipt()
        self._claim(receipt)
        task = self.tasks.read(self.name)
        if receipt is None:
            if task is not None:
                raise InstallationError('FOREIGN_SERVICE_DEFINITION', 'The unowned task was preserved.')
            return
        if receipt.get('enablement') is not None:
            raise InstallationError('SERVICE_ENABLEMENT_PENDING', 'Complete the retained enable/disable operation before removing the integration.')
        if task is not None:
            if task.digest != receipt.get('native_digest'):
                raise InstallationError('SERVICE_DEFINITION_CHANGED', 'The selected task differs from its retained receipt; reconcile it before removing it.')
            if task.active or task.state == 0:
                raise InstallationError('SUPERVISOR_STILL_ACTIVE', 'Wait for the canonical drain and foreground task to exit; no forced stop was requested.')
            atomic_json(self.path, {**receipt, 'state': 'removing'})
            self.tasks.delete(self.name, receipt['native_digest'])
            if self.tasks.read(self.name) is not None:
                raise InstallationError('UNINSTALL_UNCONFIRMED', 'Repeat uninstall to observe the same task removal.')
        # Positive native absence recovers a response lost during removal. Keep
        # context, logs, DB, credentials and shutdown evidence for foreground use.
        self.database_claim.unlink(missing_ok=True)
        self.path.unlink()
        (self.home / CONTROL_NAME).unlink(missing_ok=True)


def installation_failure(result, error):
    if isinstance(error, InstallationError):
        code, action = error.code, error.action
    elif isinstance(error, TaskConflict):
        code, action = 'SERVICE_DEFINITION_CHANGED', str(error)
    else:
        code, action = 'SUPERVISOR_UNAVAILABLE', 'Inspect Task Scheduler and the retained installation receipt before retrying; no detached fallback was used.'
    return {**result, 'state': 'failed', 'reason': code, 'next_action': action}
