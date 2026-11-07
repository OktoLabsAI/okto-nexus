"""Reviewed, partial remote bootstrap over canonical identity and Finish services.

The checkpoint is not an execution grant. Only the original successful creator
receives key material, after its transaction commits; recovery never rotates it.
"""
from copy import deepcopy
from datetime import datetime, timezone
import secrets

from nexus_connector_core import CoreError
from nexus_connector_core.connection_configuration import parse_portable_connection_configuration

from ..domain.permissions import PERMISSION_REGISTRY, PermissionSet
from ..errors import ErrorCode, OktoNexusError
from .agent_creation import create_agent_in_uow
from .auth import AgentKeyAuthService
from .connection_setup import require_operator, setup_actor
from .project_preset import ORIGIN, identity_defaults
from .remote_setup_contract import (
    ContractError, _bounded, _hash, _identifier, build_review, normalize_choices,
    normalize_draft, reference, validate_review,
)
from .terminal_connection import document_revision


def _conflict(reason):
    raise OktoNexusError(ErrorCode.CONFLICT,
        'Remote setup changed; review the affected choices before continuing.', {'reason': reason})


def effective_snapshot(agent):
    permissions = PermissionSet(agent.permissions)
    return dict(role=agent.role or 'Agent', permissions={group: {
        flag: permissions.limit(flag) if group == 'limits' else permissions.allows(group, flag)
        for flag in flags} for group, flags in PERMISSION_REGISTRY.items()}, defaults_hash=None)


class RemoteSetupService:
    def __init__(self, *, deps, access, settings):
        self.deps, self.access, self.settings = deps, access, settings
        self.repo = deps.repos.remote_setup

    def _load(self, uow, context, ref):
        require_operator(self.access, context, uow)
        record = self.repo.get(uow, actor=setup_actor(context), setup_run_id=ref['setup_run_id'])
        if record is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Remote setup review was not found.', {})
        if ref.get('review_revision') not in (None, record['current_review_revision']):
            _conflict('REVIEW_CHANGED')
        validate_review(record['review'])
        return record

    def _identity(self, uow, agent_id):
        agent = self.deps.repos.agents.get(uow, agent_id)
        if agent is None or not agent.is_active or not agent.api_key_hash:
            _conflict('IDENTITY_UNAVAILABLE')
        return agent

    def _workspace(self, uow, workspace_id):
        if self.deps.repos.workspaces.get(uow, workspace_id) is None:
            _conflict('WORKSPACE_UNAVAILABLE')

    def review(self, context, body):
        body = _bounded(body)
        if type(body) is not dict or set(body) - {'draft', 'identity', 'workspace', 'expected_review_revision'} or not {'draft', 'identity', 'workspace'} <= set(body):
            raise ContractError()
        draft = normalize_draft(body['draft'])
        identity, workspace = normalize_choices(body['identity'], body['workspace'])
        expected_revision = body.get('expected_review_revision')
        if expected_revision is not None:
            _hash(expected_revision, prefixed=False)
        request_hash = document_revision(dict(draft=draft, identity=identity, workspace=workspace))
        with self.deps.connection_factory.unit_of_work() as uow:
            require_operator(self.access, context, uow)
            actor = setup_actor(context)
            previous = self.repo.get(uow, actor=actor, setup_run_id=draft['setup_run_id'])
            if previous is not None:
                if expected_revision is None:
                    if request_hash != previous['request_hash']:
                        _conflict('EXPLICIT_REVIEW_REQUIRED')
                    return dict(state='reviewed', review=previous['review'])
                if expected_revision != previous['current_review_revision']:
                    if (previous['previous_review_revision'] == expected_revision
                            and previous['request_hash'] == request_hash):
                        return dict(state='reviewed', review=previous['review'])
                    _conflict('REVIEW_CHANGED')
                if previous['final_binding'] is not None:
                    _conflict('SETUP_ALREADY_COMMITTED')
                old = previous['review']
                # These objects already belong to this root. A revised draft may
                # not adopt a different identity, workspace or remote machine.
                if previous['bootstrap'] is not None and (
                        identity != old['selection']['identity'] or workspace != old['selection']['workspace']
                        or draft['connector_id'] != old['draft']['connector_id']
                        or draft['server_origin'] != old['draft']['server_origin']):
                    _conflict('SETUP_SCOPE_CHANGED')
            elif expected_revision is not None:
                _conflict('REVIEW_UNAVAILABLE')
            server = self.repo.server_id(uow)
            boot = previous['bootstrap'] if previous else None
            if identity['mode'] == 'create' and boot is None:
                if self.repo.occupied_agent(uow, agent_id=identity['agent_id']):
                    _conflict('AGENT_ID_OCCUPIED')
                snapshot, epoch = identity_defaults(), 0
            else:
                agent = self._identity(uow, identity['agent_id'])
                snapshot = effective_snapshot(agent)
                revisions = self.repo.credential(uow, agent_id=agent.agent_id, persist=True)
                epoch = revisions['credential_epoch']
                if boot is not None and epoch != boot['credential_epoch']:
                    _conflict('BOOTSTRAP_CREDENTIAL_CHANGED')
            if workspace['mode'] == 'select':
                self._workspace(uow, workspace['workspace_id'])
            if boot is not None:
                self._workspace(uow, boot['workspace_id'])
            policy = self.settings.native_decision_review(uow)
            policy = dict(expected_revision=policy['revision'], initialize=policy['can_initialize'])
            self.settings.validate_native_decisions(uow, policy)
            machines = self.repo.machine_review(uow, agent_id=identity['agent_id'], connector_id=draft['connector_id'])
            machine_policy = self.deps.config.remote_machine_policy
            if machine_policy == 'deny' and machines:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Remote machine replacement is denied by current policy.', {})
            selection = dict(server_id=server, identity=identity, workspace=workspace,
                credential=dict(mode='issue_once' if identity['mode'] == 'create' else 'reuse_existing',
                    expected_epoch=0 if identity['mode'] == 'create' else epoch),
                baseline=self.repo.baseline(uow, agent_id=identity['agent_id']),
                native_decision_policy=policy, project_preset=dict(ORIGIN), identity_snapshot=snapshot,
                remote_machine_policy=machine_policy, previous_machines=machines)
            children = None
            if previous is not None:
                children = deepcopy(previous['review']['child_requests'])
                # A parent revision is in prepare's payload. Preserve registration
                # and unchanged realization; new IDs are committed once and then
                # read on retries. Old proposals/children remain immutable.
                suffix = document_revision(dict(previous=previous['current_review_revision'],
                    draft=draft, selection=selection))[:24]
                if draft != previous['review']['draft'] or selection != previous['review']['selection']:
                    for phase in ('prepare', 'apply'):
                        children[phase] = draft['setup_run_id'] + '_' + phase + '_' + suffix
                    fields = ('installation', 'local_consent', 'configuration', 'project_label')
                    if any(draft[key] != previous['review']['draft'][key] for key in fields):
                        children['realize'] = draft['setup_run_id'] + '_realize_' + suffix
            review = build_review(draft, selection, children=children)
            self.repo.save_review(uow, actor=actor, review=review, request_hash=request_hash,
                expected_revision=previous['current_review_revision'] if previous else None,
                now=self.deps.clock.now_iso())
        return dict(state='reviewed', review=review)

    def bootstrap(self, context, body):
        ref = reference(body)
        material = None
        with self.deps.connection_factory.unit_of_work() as uow:
            record = self._load(uow, context, ref)
            if record['bootstrap'] is not None:
                return self._envelope(uow, record)
            selection = record['review']['selection']
            identity, workspace = selection['identity'], selection['workspace']
            agent_id = identity['agent_id']
            if self.repo.server_id(uow) != selection['server_id']:
                _conflict('SERVER_CHANGED')
            if self.repo.baseline(uow, agent_id=agent_id) != selection['baseline']:
                _conflict('BASELINE_CHANGED')
            self.settings.validate_native_decisions(uow, selection['native_decision_policy'])
            if (selection['remote_machine_policy'] != self.deps.config.remote_machine_policy
                    or selection['previous_machines'] != self.repo.machine_review(uow,
                        agent_id=agent_id, connector_id=record['review']['draft']['connector_id'])):
                _conflict('REMOTE_MACHINE_POLICY_CHANGED')

            if identity['mode'] == 'create':
                if self.repo.occupied_agent(uow, agent_id=agent_id):
                    _conflict('AGENT_ID_OCCUPIED')
                if identity_defaults() != selection['identity_snapshot']:
                    _conflict('IDENTITY_DEFAULTS_CHANGED')
            else:
                agent = self._identity(uow, agent_id)
                current = self.repo.credential(uow, agent_id=agent_id, persist=False)
                if (effective_snapshot(agent) != selection['identity_snapshot']
                        or current['credential_epoch'] != selection['credential']['expected_epoch']
                        or current['anchored_epoch'] != current['credential_epoch']):
                    _conflict('IDENTITY_CHANGED')
            if workspace['mode'] == 'select':
                self._workspace(uow, workspace['workspace_id'])
            self.access.authorize_maintenance(context, uow=uow)
            if identity['mode'] == 'create':
                snapshot = selection['identity_snapshot']
                _, key = create_agent_in_uow(self.deps, uow,
                    AgentKeyAuthService(self.deps.repos.agents, self.deps.clock),
                    agent_id=agent_id, role=snapshot['role'], permissions=snapshot['permissions'],
                    metadata={'display_name': identity['display_name']})
                material = dict(api_key=key)
            workspace_id = workspace['workspace_id']
            if workspace['mode'] == 'create':
                workspace_id = 'ws_' + secrets.token_hex(16)
                if self.deps.repos.workspaces.get(uow, workspace_id) is not None:
                    _conflict('WORKSPACE_ID_OCCUPIED')
                self.deps.repos.workspaces.upsert(uow, workspace_id=workspace_id,
                    display_name=workspace['display_name'])
            revisions = self.repo.credential(uow, agent_id=agent_id, persist=True)
            receipt = dict(setup_run_id=ref['setup_run_id'], review_revision=ref['review_revision'],
                server_id=selection['server_id'], agent_id=agent_id, workspace_id=workspace_id,
                credential_epoch=revisions['credential_epoch'])
            self.repo.save_bootstrap(uow, actor=setup_actor(context), setup_run_id=ref['setup_run_id'],
                revision=ref['review_revision'], receipt=receipt,
                baseline=self.repo.baseline(uow, agent_id=agent_id), now=self.deps.clock.now_iso())
            record = self.repo.get(uow, actor=setup_actor(context), setup_run_id=ref['setup_run_id'])
            response = self._envelope(uow, record)
        # No material can escape a failed commit. It is never serialized into
        # any checkpoint, audit row, proposal or idempotent response storage.
        if material is not None:
            response.update(material=material, material_status='issued_once')
        return response

    def recover(self, context, body):
        ref = reference(body, optional_revision=True)
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            operator = self.access.authenticate(context, uow=uow, require_feature=False)
            if operator:
                record = self._load(uow, context, ref)
            else:
                if context.authentication_source != 'agent_key' or not context.actor_agent_id:
                    raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Authenticate the bootstrap subject.', {})
                record = self.repo.for_subject(uow, setup_run_id=ref['setup_run_id'], agent_id=context.actor_agent_id)
                if record is None:
                    raise OktoNexusError(ErrorCode.NOT_FOUND, 'Remote setup review was not found.', {})
                if ref.get('review_revision') not in (None, record['current_review_revision']):
                    _conflict('REVIEW_CHANGED')
                validate_review(record['review'])
            return self._envelope(uow, record)

    def _references(self, uow, record):
        boot = record['bootstrap']
        if boot is None:
            return None
        selection = record['review']['selection']
        agent = self.deps.repos.agents.get(uow, boot['agent_id'])
        if (agent is None or not agent.is_active or not agent.api_key_hash
                or self.deps.repos.workspaces.get(uow, boot['workspace_id']) is None):
            return 'unavailable'
        credential = self.repo.credential(uow, agent_id=boot['agent_id'], persist=False)
        snapshot = effective_snapshot(agent)
        expected = selection['identity_snapshot']
        if (credential['server_id'] != boot['server_id']
                or credential['credential_epoch'] != boot['credential_epoch']
                or credential['anchored_epoch'] != credential['credential_epoch']
                or snapshot['role'] != expected['role'] or snapshot['permissions'] != expected['permissions']):
            return 'changed'
        return 'matching'

    def _envelope(self, uow, record):
        boot, review = record['bootstrap'], record['review']
        canonical = self.repo.materialization(uow, record=record) if boot else None
        final = record['final_binding'] or (canonical['final_binding'] if canonical else None)
        return dict(state='committed' if final else 'awaiting_host' if boot else 'reviewed',
            review=deepcopy(review), bootstrap=deepcopy(boot),
            handoff=(dict(format='okto.remote-setup-handoff', version=1, bootstrap=deepcopy(boot),
                review_revision=review['review_revision'], child_requests=deepcopy(review['child_requests']),
                draft_revision=review['draft_revision']) if boot else None),
            material=None, material_status=('not_issued' if not boot else 'unavailable'
                if review['selection']['identity']['mode'] == 'create' else 'reuse_existing'),
            final_binding=final, current_references=self._references(uow, record))

    def materialization(self, context, body):
        body = _bounded(body)
        if type(body) is not dict or set(body) - {'setup_run_id', 'review_revision', 'proposal_id'}:
            raise ContractError()
        ref = reference({key: value for key, value in body.items() if key != 'proposal_id'})
        proposal_id = body.get('proposal_id')
        if proposal_id is not None:
            _identifier(proposal_id)
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            record = self._load(uow, context, ref)
            canonical = self.repo.materialization(uow, record=record, proposal_id=proposal_id)
            changed, missing = [], []
            fields = None
            if canonical is None:
                missing.append('canonical_child_proposal')
            else:
                fields = self._compare(uow, record, canonical, changed, missing)
            return dict(state='requires_review' if changed else 'needs_canonical_metadata' if missing else 'review_matches',
                changed_fields=sorted(set(changed)), missing_fields=sorted(set(missing)), canonical_fields=fields,
                proposal=deepcopy(canonical['proposal']) if canonical else None,
                approval_id=canonical['approval_id'] if canonical else None,
                final_binding=canonical['final_binding'] if canonical else None,
                comparison_only=True, authority_granted=False, requires_authenticated_operator=True)

    def _compare(self, uow, record, canonical, changed, missing):
        review, boot = record['review'], record['bootstrap']
        draft, selection = review['draft'], review['selection']
        proposal, expected = canonical['proposal'], canonical['expected']
        fields = deepcopy(expected) | {key: proposal.get(key) for key in (
            'server_id', 'agent_id', 'workspace_id', 'executor_id', 'workspace_binding_id',
            'adapter_id', 'candidate_ref', 'inventory_revision', 'realization_ref',
            'binding_id', 'endpoint_id', 'profile_id', 'proposal_id', 'proposal_revision')}
        fields.update(connector_id=canonical['connector_id'], local_consent_id=canonical['local_consent_id'])
        for key in ('server_id', 'agent_id', 'workspace_id'):
            if proposal.get(key) != boot[key]:
                changed.append(key)
        for key in ('adapter_id', 'candidate_ref'):
            if proposal.get(key) != draft['installation'][key]:
                changed.append('installation.' + key)
        if canonical['connector_id'] != draft['connector_id']:
            changed.append('connector_id')
        for key, actual in [('local_consent_id', canonical['local_consent_id']),
                ('local_root_proof_digest', canonical['root_proof_digest']),
                ('configuration_digest', canonical['configuration_digest'])]:
            reviewed = draft['local_consent'][key]
            if reviewed is not None and reviewed != actual:
                changed.append('local_consent.' + key)
        inventory = draft['installation']['inventory_revision']
        if inventory is not None and inventory != proposal.get('inventory_revision'):
            changed.append('installation.inventory_revision')
        try:
            portable = parse_portable_connection_configuration(expected['connection_configuration'])
        except (KeyError, TypeError, ValueError, CoreError):
            missing.append('connection_configuration')
        else:
            if portable != draft['configuration']:
                changed.append('configuration')
        for key in ('project_preset', 'native_decision_policy'):
            if expected.get(key) != selection[key]:
                changed.append(key)
        if expected.get('previous_machines', []) != selection['previous_machines']:
            changed.append('previous_machines')
        if (self.deps.config.remote_machine_policy != selection['remote_machine_policy']
                or expected.get('previous_machines') and expected.get('remote_machine_policy') != selection['remote_machine_policy']):
            changed.append('remote_machine_policy')
        if self._references(uow, record) != 'matching':
            changed.append('identity_or_workspace')
        if canonical['final_binding'] is None:
            baseline = self.repo.baseline(uow, agent_id=boot['agent_id'])
            reviewed_baseline = selection['baseline'] if review['review_revision'] != boot['review_revision'] else record['bootstrap_baseline']
            if baseline != reviewed_baseline:
                changed.append('baseline')
            if canonical['status'] != 'PREPARED' or not proposal.get('can_apply'):
                changed.append('proposal_state')
            try:
                expiry = datetime.fromisoformat(canonical['expires_at'].replace('Z', '+00:00'))
                now = datetime.fromisoformat(self.deps.clock.now_iso().replace('Z', '+00:00'))
                if expiry.tzinfo is None or expiry <= now.astimezone(timezone.utc):
                    changed.append('proposal_expired')
            except (TypeError, ValueError):
                missing.append('proposal_expiry')
            if not canonical['approval_id']:
                missing.append('operator_approval')
        return fields
