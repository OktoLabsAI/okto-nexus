"""Host-owned, resumable environment replacement; never admits runtime work."""
from __future__ import annotations

import copy
import json
import re
import secrets
from pathlib import Path

from nexus_connector_core.user_service_definition import windows_with_execution, windows_execution_matches, windows_definition_digest

from .service_environment import installed_versions, probe, release_version


class UpgradeError(ValueError):
    def __init__(self, code, action):
        super().__init__(code)
        self.code, self.action = code, action


def fail(code, action):
    raise UpgradeError(code, action)


def save_plan(path, document):
    """Save the review document exclusively, without shell encoding changes."""
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


class ServiceUpgrade:
    def __init__(self, host):
        self.host = host

    def _target(self, source, candidate):
        return {**copy.deepcopy(source), 'revision': 2, 'executable': candidate['executable'],
            'environment_prefix': candidate['environment_prefix'],
            'package_version': candidate['package']['version'], 'core_version': candidate['core']['version'],
            'environment_fingerprint': self.host.digest(candidate)}

    def _versions(self, source_version, source_core, candidate):
        if release_version(candidate['package']['version']) < release_version(source_version):
            fail('UPGRADE_DOWNGRADE_REFUSED', 'Binary downgrade requires a separately reviewed data recovery procedure.')
        if release_version(candidate['core']['version']) < release_version(source_core):
            fail('UPGRADE_DOWNGRADE_REFUSED', 'Core downgrade requires a separately reviewed journal recovery procedure.')

    def plan(self, executable):
        h = self.host
        source = h.read(h.context_path)
        if source.get('upgrade_pending'):
            fail('SERVICE_UPGRADE_PENDING', 'Resume the retained plan before selecting another environment.')
        h.validate(source, require_paths=False)
        observed = h.status()
        receipt, task = h.installed()
        if receipt and h.digest(source) != receipt.get('context_digest'):
            fail('SERVICE_CONTEXT_CHANGED', 'Restore or explicitly reconcile the recorded context before upgrading.')
        candidate = probe(executable)
        source_version, source_core = source.get('package_version'), source.get('core_version')
        if not source_version or not source_core:
            source_version, source_core = installed_versions(source['executable'])
        source_version = observed.get('active_version') or source_version
        self._versions(source_version, source_core, candidate)
        target = self._target(source, candidate)
        h.validate(target)
        generation = observed.get('generation') or None
        marker = h.optional(h.run_path)
        if not generation and marker.get('state') == 'drained' and marker.get('instance_id') == h.instance_id:
            generation = marker.get('generation')
        if h.runtime_exists() and not generation:
            fail('UPGRADE_DRAIN_UNCONFIRMED',
                'Plan from the running source environment, then drain that generation with its matching CLI. No process was started.')
        body = {'revision': 1, 'component': h.component, 'instance_id': h.instance_id,
            'source_context': source, 'target_context': target, 'candidate': candidate,
            'source_receipt': receipt, 'source_claim': h.claim_snapshot(receipt),
            'source_launch': h.optional(h.launch_path),
            'source_generation': generation, 'source_version': source_version, 'source_core_version': source_core,
            'target_token': secrets.token_hex(16)}
        if task:
            body['source_native_xml'] = task.xml
            body['source_native_digest'] = task.digest
            definition = h.definition(target, body['target_token'])
            if not Path(definition.executable).is_file():
                fail('SERVICE_EXECUTABLE_MISSING', 'The target user-task environment needs its consoleless executable.')
            h.validate_native(h.propose(task.xml, definition))
        if len(json.dumps(body).encode('utf-8')) > 60000:
            fail('UPGRADE_PLAN_TOO_LARGE', 'The complete reviewed plan exceeds the retained receipt budget.')
        return {'plan_revision': h.digest(body), 'plan': body,
            'next_action': 'Review this plan, drain the source generation, then upgrade-apply with this exact plan revision. Start afterward is explicit.'}

    def apply(self, document, expected_revision):
        h = self.host
        body = document.get('plan') if isinstance(document, dict) else None
        if not isinstance(body, dict) or h.digest(body) != expected_revision or document.get('plan_revision') != expected_revision:
            fail('UPGRADE_PLAN_CONFLICT', 'Use the exact reviewed plan and its plan_revision.')
        if (body.get('revision') != 1 or body.get('component') != h.component or body.get('instance_id') != h.instance_id):
            fail('UPGRADE_INSTANCE_MISMATCH', 'The plan does not select this component and canonical instance.')
        if (not re.fullmatch(r'[a-f0-9]{32}', str(body.get('target_token', '')))
                or not isinstance(body.get('source_launch'), dict)
                or body.get('source_generation') is not None and (not isinstance(body['source_generation'], str)
                    or not 1 <= len(body['source_generation']) <= 128)
                or body.get('source_receipt') is not None and not isinstance(body['source_receipt'], dict)
                or body.get('source_claim') is not None and not isinstance(body['source_claim'], dict)):
            fail('UPGRADE_PLAN_CONFLICT', 'The reviewed plan contains invalid lifecycle references.')
        source, target = body['source_context'], body['target_context']
        if (not isinstance(source, dict) or not isinstance(target, dict)
                or target != self._target(source, body['candidate'])
                or len(json.dumps(body).encode('utf-8')) > 60000):
            fail('UPGRADE_PLAN_CONFLICT', 'The plan may replace only the selected installed environment.')
        self._versions(body['source_version'], body['source_core_version'], body['candidate'])
        h.validate(source, require_paths=False)
        h.validate(target)
        if body.get('source_receipt'):
            receipt = body['source_receipt']
            if (receipt.get('native_xml') != body.get('source_native_xml')
                    or receipt.get('native_digest') != body.get('source_native_digest')
                    or windows_definition_digest(body.get('source_native_xml')) != body.get('source_native_digest')):
                fail('UPGRADE_PLAN_CONFLICT', 'The reviewed source export and ownership receipt do not match.')
            definition = h.definition(target, body['target_token'])
            if not Path(definition.executable).is_file():
                fail('SERVICE_EXECUTABLE_MISSING', 'Restore the reviewed target consoleless Python before applying.')
            h.propose(body['source_native_xml'], definition)
        current = h.read(h.context_path)
        completed = h.optional(h.completed_path)
        if current == target and completed.get('plan_revision') == expected_revision and completed.get('state') == 'committed':
            if probe(target['executable']) != body['candidate']:
                fail('UPGRADE_TARGET_CHANGED', 'Restore the reviewed environment before confirming this completed upgrade.')
            h.check_committed(completed)
            return {'applied': True, 'changed': False, 'plan_revision': expected_revision,
                    'migration_state': 'not_run_by_upgrade', 'next_action': 'Use explicit start; canonical startup owns migrations and runtime reconciliation.'}
        # The host holds both launch exclusion and OS lifetime locks until the
        # context is unfrozen. It never holds a database transaction or waits for
        # network/provider work here.
        with h.exclusion():
            if probe(target['executable']) != body['candidate']:
                fail('UPGRADE_TARGET_CHANGED', 'The reviewed target changed before acquiring instance exclusion.')
            current = h.read(h.context_path)
            frozen = current.get('upgrade_pending')
            if frozen:
                if frozen != expected_revision or current.get('upgrade_plan') != body:
                    fail('SERVICE_UPGRADE_PENDING', 'A different retained upgrade must be completed first.')
                retained = {key: value for key, value in current.items() if key != 'confirmed_receipt'}
                if retained != {**source, 'revision': 2, 'upgrade_pending': expected_revision, 'upgrade_plan': body}:
                    fail('UPGRADE_CONTEXT_CONFLICT', 'The pending context changed after fencing; the edit was preserved.')
            else:
                if current != source:
                    fail('UPGRADE_CONTEXT_CONFLICT', 'The source context changed after review; it was preserved.')
                if body.get('source_generation'):
                    marker = h.optional(h.run_path)
                    if marker and (marker.get('generation') != body['source_generation']
                            or marker.get('state') != 'drained' or marker.get('instance_id') != h.instance_id):
                        fail('UPGRADE_DRAIN_UNCONFIRMED', 'A newer or unconfirmed generation must be drained and reviewed first.')
                    shutdown = h.optional(h.shutdown_path)
                    if shutdown.get('generation') != body['source_generation'] or shutdown.get('state') != 'DRAINED':
                        fail('UPGRADE_DRAIN_UNCONFIRMED', 'Complete canonical drain of the reviewed source generation before applying.')
                elif h.runtime_exists():
                    fail('UPGRADE_DRAIN_UNCONFIRMED', 'Runtime state appeared after review; plan and drain that generation first.')
                h.check_source(body)
                # This single atomic write is the durable fence. Revision 2
                # rejects old revision-1 managed entrypoints; current entrypoints
                # refuse upgrade_pending before bootstrap.
                current = {**source, 'revision': 2, 'upgrade_pending': expected_revision, 'upgrade_plan': body}
                h.write(h.context_path, current)
            receipt = body.get('source_receipt')
            confirmed = None
            h.check_resume(body, current.get('confirmed_receipt'))
            if receipt:
                task = h.native_read()
                if task is None:
                    fail('UPGRADE_NATIVE_UNCONFIRMED', 'The owned task disappeared. Retain the plan and reconcile the selected definition.')
                if task.active or task.state == 0:
                    fail('UPGRADE_NATIVE_UNCONFIRMED', 'Wait until the selected task is observably inactive; no forced stop was requested.')
                definition = h.definition(target, body['target_token'])
                desired = h.propose(body['source_native_xml'], definition)
                if task.digest == body['source_native_digest']:
                    h.native_replace(task.digest, desired)
                    task = h.native_read()
                if task is None or not h.matches(body['source_native_xml'], task.xml, definition):
                    fail('UPGRADE_NATIVE_CONFLICT', 'The observed task differs from the retained action-only intent. It was not adopted.')
                confirmed = {**receipt, 'token': body['target_token'], 'state': 'installed',
                    'context_digest': h.digest(target), 'definition_digest': definition.revision_digest,
                    'native_xml': task.xml, 'native_digest': task.digest}
                # Persist the observed result before publishing any other files.
                current = {**current, 'confirmed_receipt': confirmed}
                h.write(h.context_path, current)
                h.publish_installation(body, confirmed)
            h.fence_old_launch(body['target_token'])
            completed = {'revision': 1, 'state': 'committed', 'plan_revision': expected_revision,
                'plan': body, 'confirmed_receipt': confirmed, 'migration_state': 'not_run_by_upgrade'}
            h.write(h.completed_path, completed)
            h.write(h.context_path, target)  # last: release the durable startup fence
        return {'applied': True, 'changed': True, 'plan_revision': expected_revision,
            'target_version': body['candidate']['package']['version'],
            'migration_state': 'not_run_by_upgrade',
            'next_action': 'Start explicitly with the target environment. Do not roll back binaries after an incompatible migration; use the retained source references only for reviewed recovery.'}

class UpgradeHost:
    """Filesystem/native effects owned by the application, under its guards."""
    propose = staticmethod(windows_with_execution)
    matches = staticmethod(windows_execution_matches)

    def optional(self, path):
        try:
            return self.read(path)
        except FileNotFoundError:
            return {}

    def installed(self):
        return self.installation.observe(check_context=False)

    def definition(self, context, token):
        return self.installation.definition(context, token)

    def validate_native(self, xml):
        self.installation.tasks.validate(self.installation.name, xml)

    def native_read(self):
        return self.installation.tasks.read(self.installation.name)

    def native_replace(self, expected, xml):
        return self.installation.tasks.replace(self.installation.name, expected, xml)

    def check_source(self, body):
        receipt, task = self.installed()
        if receipt != body.get('source_receipt') or (task and task.digest != body.get('source_native_digest')):
            fail('UPGRADE_NATIVE_CONFLICT', 'The selected installation changed after review.')
        if task and (task.active or task.state == 0):
            fail('UPGRADE_NATIVE_UNCONFIRMED', 'Drain the selected task and wait for native exit before applying.')
        self.check_resume(body, None)
        launch = self.optional(self.launch_path)
        if launch.get('state') == 'pending':
            fail('UPGRADE_LAUNCH_PENDING', 'Resolve the retained detached launch before applying this upgrade.')

    def check_resume(self, body, confirmed):
        receipt = self.optional(self.installation_path) or None
        allowed = (body.get('source_receipt'), confirmed) if confirmed else (body.get('source_receipt'),)
        if receipt not in allowed:
            fail('UPGRADE_RECEIPT_CONFLICT', 'The retained installation receipt changed; it was preserved.')
        self.check_claim(body, confirmed)
        if body.get('source_receipt'):
            control = self.read(self.control_path)
            tokens = {body['source_receipt']['token'], body['target_token']}
            if control.get('token') not in tokens or control.get('launch_requested'):
                fail('UPGRADE_CONTROL_CONFLICT', 'Complete canonical stop or reconcile the retained control receipt.')
        elif self.optional(self.control_path):
            fail('UPGRADE_CONTROL_CONFLICT', 'A control receipt exists without the reviewed installation.')

    def publish_installation(self, body, confirmed):
        self.check_resume(body, confirmed)
        self.publish_claim(body, confirmed)
        self.write(self.installation_path, confirmed)
        self.write(self.control_path, {'revision': 1, 'token': confirmed['token'],
            'desired': 'draining', 'generation': None, 'logon_session': self.logon_session()})

    def fence_old_launch(self, token):
        self.write(self.launch_path, {'revision': 1, 'instance_id': self.instance_id,
            'token': token, 'state': 'upgrade_complete'})

    def check_committed(self, document):
        confirmed = document.get('confirmed_receipt')
        receipt, task = self.installed()
        if receipt != confirmed or (task and task.digest != confirmed['native_digest']):
            fail('UPGRADE_RECEIPT_CONFLICT', 'The completed installation changed; no repeat mutation was attempted.')
        self.check_claim(document['plan'], confirmed, committed=True)
