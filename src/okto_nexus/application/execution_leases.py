"""Canonical grant evaluation and durable, correlated R4 lease application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import secrets
import time

from nexus_connector_core import R4_PREVIEW_REVISION, decode_r4_frame, encode_r4_frame
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .executor_inventory import load_current_executor_inventory


# Canonical delegation verbs retain their existing semantics. Native response
# verbs below allow transport only; their dispatch additionally requires the
# committed operator decision, original request, and current operator proof.
_ACTIONS = {'open': 'runtime.open', 'send': 'turn.submit', 'steer': 'turn.steer',
            'interrupt': 'turn.interrupt', 'close': 'runtime.close'}


@dataclass(frozen=True, slots=True)
class ExecutionChannel:
    """Host-authenticated source; never constructed from a received frame."""
    server_id: str
    executor_id: str
    connection_id: str
    connection_generation: int


def _conflict(message):
    return OktoNexusError(ErrorCode.CONFLICT, message, {})


def _stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def require_execution_lane(uow, *, scope, channel, now):
    """Revalidate the binding ticket inside the effect authorization transaction."""
    lane = SqliteExecutionLeaseRepository().lane(uow, scope)
    if (lane is None or lane['state'] != 'ADMITTED' or lane['agent_id'] != scope['agent_id'] or
            lane['connection_id'] != channel.connection_id or
            lane['connection_generation'] != channel.connection_generation or
            lane['bound_connection_id'] != channel.connection_id or lane['revoked_at'] is not None or
            'lease:request' not in json.loads(lane['scopes_json']) or
            any(lane[k] != scope[k] for k in ('authorization_revision','configuration_revision','credential_epoch'))):
        raise _conflict('An admitted binding lane with lease authority is required.')
    expires = min(_stamp(lane['expires_at']), _stamp(lane['ticket_expires_at']))
    if expires <= now:
        raise _conflict('The binding lane authority has expired.')
    return expires


class ExecutionLeaseService:
    def __init__(self, *, factory, access, fresh_publications, max_duration_ms=120000):
        if type(max_duration_ms) is not int or not 1000 <= max_duration_ms <= 120000:
            raise ValueError('The lease duration must be between 1000 and 120000 milliseconds.')
        self.factory, self.access = factory, access
        self.fresh_publications = fresh_publications
        self.max_duration_ms = max_duration_ms
        self.repo = SqliteExecutionLeaseRepository()

    def _parse(self, frame, kind, channel):
        frame = decode_r4_frame(encode_r4_frame(frame))
        if frame['type'] != kind or not isinstance(channel, ExecutionChannel):
            raise _conflict('Invalid lease frame or source channel.')
        scope = frame['scope']
        if (scope['server_id'] != channel.server_id or scope['executor_id'] != channel.executor_id or
                frame['connection_id'] != channel.connection_id or
                frame['connection_generation'] != channel.connection_generation):
            raise _conflict('The lease source channel changed.')
        # Refresh derived revisions before the short issuance transaction.
        server_id, revisions, _ = current_agent_revisions(self.factory, agent_id=scope['agent_id'])
        if (server_id != channel.server_id or
                (revisions.authorization, revisions.configuration, revisions.credential_epoch) !=
                (scope['authorization_revision'], scope['configuration_revision'], scope['credential_epoch'])):
            raise _conflict('The lease authority changed.')
        return frame

    def _authority(self, uow, scope, grant_id, channel, now):
        from .execution_agent_recovery import require_agent_ready
        require_agent_ready(uow.connection, scope['server_id'], scope['executor_id'], scope['agent_id'])
        row = self.repo.authority(uow, scope)
        if (row is None or not row['is_active'] or not row['api_key_hash'] or
                row['agent_id'] != scope['agent_id'] or row['subject_agent_id'] != scope['agent_id'] or
                row['binding_id'] != scope['binding_id'] or row['workspace_id'] != scope['workspace_id'] or
                row['workspace_binding_id'] != scope['workspace_binding_id'] or
                row['binding_workspace_binding_id'] != scope['workspace_binding_id'] or
                row['realization_workspace_binding_id'] != scope['workspace_binding_id'] or
                row['owner_generation'] != scope['session_owner_generation'] or
                row['binding_revision'] != scope['binding_revision'] or
                row['protocol'] != 'nxl-r4' or row['activation_state'] != 'approved' or not row['enabled'] or
                row['health'] == 'quarantined' or row['workspace_status'] != 'READY' or
                row['realization_status'] != 'READY' or row['realization_revision'] != row['current_realization_revision'] or
                row['revoked_at'] is not None or row['control_state'] != 'CONTROL_READY' or
                row['generation'] != channel.connection_generation or row['owner_instance_id'] != channel.connection_id or
                row['lifecycle_state'] not in ('OPEN_PENDING', 'READY') or
                row['admission_state'] not in ('ACCEPTED', 'DISPATCH_PENDING', 'DISPATCHED', 'RESOLVED_TERMINAL') or
                not row['source_guard_digest'] or row['source_guard_digest'] != _agent_guard(uow.connection, scope['agent_id']) or
                json.loads(row['expected_revisions_json']) != scope):
            raise _conflict('The admitted session authority is no longer current.')
        from .execution_operator_authority import require_recorded_operator
        require_recorded_operator(uow, actor=row['actor_agent_id'], subject=scope['agent_id'],
                                  guard=row['actor_guard_digest'], access=self.access)
        source = self.repo.source_grant(uow, grant_id)
        if row['dispatch_grant_id'] is not None and row['dispatch_grant_id'] != grant_id:
            raise _conflict('The lease grant does not match the dispatched operation.')
        if (source is None or source['revoked_at'] is not None or (not source['no_expiry'] and _stamp(source['expires_at']) <= now) or
                source['actor_agent_id'] != scope['agent_id'] or source['represented_agent_id'] != scope['agent_id'] or
                source['endpoint_id'] != row['endpoint_id'] or source['workspace_id'] != scope['workspace_id'] or
                source['credential_binding'] != row['api_key_hash']):
            raise _conflict('A current canonical execution grant is required.')
        expires = (now + timedelta(milliseconds=self.max_duration_ms)
                   if source['no_expiry'] else _stamp(source['expires_at']))
        if row["lifecycle_state"] == "OPEN_PENDING":
            from .execution_domain_delivery import require_domain_delivery
            require_domain_delivery(uow, access=self.access, server_id=scope["server_id"],
                executor_id=scope["executor_id"], operation_id=row["open_operation_id"])
        if row["boot_authority_json"] is not None and row["lifecycle_state"] == "OPEN_PENDING":
            from .execution_boot_authority import require_boot_authority
            require_boot_authority(uow, access=self.access, agent_id=scope["agent_id"],
                endpoint_id=row["endpoint_id"], proof=json.loads(row["boot_authority_json"]))
        if row["connection_key_id"] is not None:
            from .execution_connection_keys import require_connection_key
            key = require_connection_key(uow, access=self.access,
                agent_id=scope["agent_id"], endpoint_id=row["endpoint_id"],
                key_id=row["connection_key_id"])
            if key["source_grant_id"] is not None and key["source_grant_id"] != grant_id:
                raise _conflict('The opening connection grant changed.')
            if key["expires_at"] is not None:
                expires = min(expires, _stamp(key["expires_at"]))
        if row['kind'] == 'remote':
            expires = min(expires, require_execution_lane(uow, scope=scope, channel=channel, now=now))
        if expires <= now:
            raise _conflict('The lease authority has expired.')
        inventory = self.repo.inventory(uow, scope)
        fresh = self.fresh_publications.get((scope['server_id'], scope['executor_id']))
        from .execution_inventory_revalidation import accepts_binding
        if (inventory is None or fresh is None or fresh[0] != inventory['publication_sequence'] or
                not accepts_binding(uow.connection, row, inventory['inventory_revision'], scope['server_id'], scope['executor_id']) or
                inventory['observation_age_ms'] + max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120000):
            raise _conflict('The lease inventory is no longer fresh.')
        snapshot = load_current_executor_inventory(inventory['canonical_projection'])
        if not any(item['candidate_ref'] == row['candidate_ref'] and item['adapter_id'] == row['adapter_id']
                   for item in snapshot['evidence']):
            raise _conflict('The lease candidate changed.')
        # The lane has authenticated the current agent epoch. The canonical
        # access service still verifies credential binding, delegation, policy,
        # profile and endpoint for each granted action inside this transaction.
        context = RuntimeRequestContext(
            scope['agent_id'], 'agent_key', execution_grant_id=grant_id,
            credential_binding=row['api_key_hash'], represented_agent_id=scope['agent_id'],
            workspace_id=scope['workspace_id'], endpoint_id=row['endpoint_id'])
        semantic = json.loads(row['semantic_payload'])
        if semantic['action'] != 'runtime.open':
            raise _conflict('The session has no canonical opening operation.')
        actions = []
        for action in json.loads(source['actions']):
            if action not in _ACTIONS:
                continue
            self.access.authorize(
                context, action=action, endpoint_id=row['endpoint_id'],
                represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'],
                substrate='attach' if semantic['payload']['mode'] == 'attach' else 'managed',
                uow=uow, audit=False, check_budget=False)
            actions.append(_ACTIONS[action])
        if (self.access.config.feature_hitl and 'turn.submit' in actions and
                row['adapter_id'] in {'codex_app_server', 'claude_stream', 'pi_rpc'}):
            actions.extend(('approval.decide', 'input.provide'))
        if row['lifecycle_state'] == 'OPEN_PENDING' and 'runtime.open' not in actions:
            raise _conflict('The canonical grant does not authorize opening this session.')
        return row, source, sorted(set(actions)), expires

    def issue(self, request, *, channel: ExecutionChannel):
        request = self._parse(request, 'lease.renew', channel)
        scope = request['scope']
        digest = hashlib.sha256(canonical_json(request)).hexdigest()
        with self.factory.unit_of_work() as uow:
            now = _stamp(self.access.clock.now_iso())
            authority, source, actions, expires = self._authority(uow, scope, request['grant_id'], channel, now)
            latest = self.repo.latest(uow, scope)
            prior = self.repo.request(uow, scope, request['request_id'])
            if prior is not None:
                if (prior['request_digest'] != digest or prior['status'] not in ('ISSUED','ACTIVE') or
                        latest['lease_serial'] != prior['lease_serial'] or
                        prior['source_grant_revision'] != source['revision'] or
                        json.loads(prior['allowed_actions_json']) != actions or _stamp(prior['valid_until_server']) <= now):
                    raise _conflict('The lease request cannot be replayed.')
                return json.loads(prior['grant_json'])
            serial = latest['lease_serial'] if latest is not None else 0
            if request['expected_lease_serial'] != serial:
                raise _conflict('The expected lease serial changed.')
            if latest is None:
                if request['purpose'] != 'initial' or authority['lifecycle_state'] != 'OPEN_PENDING':
                    raise _conflict('An initial opening lease is required.')
                if authority['dispatch_phase'] == 'OPEN_AUTHORIZED_PENDING_LEASE' and (
                        authority['dispatch_connection_id'] != channel.connection_id or
                        authority['dispatch_connection_generation'] != channel.connection_generation):
                    raise _conflict('The opening bootstrap belongs to a different connection.')
            else:
                if (latest['grant_id'] != request['grant_id'] or not latest['scope_json'] or
                        json.loads(latest['scope_json']) != scope or latest['status'] == 'REVOKED' or
                        _stamp(latest['valid_until_server']) <= now):
                    raise _conflict('The previous lease requires reconciliation.')
                if request['purpose'] == 'renew':
                    if (latest['status'] != 'ACTIVE' or latest['connection_id'] != channel.connection_id or
                            latest['connection_generation'] != channel.connection_generation):
                        raise _conflict('The previous lease is not applied on this connection.')
                elif request['purpose'] == 'reconnect':
                    if latest['applied_at'] is None:
                        raise _conflict('An unapplied lease requires reconciliation before reconnect.')
                    if (latest['status'] != 'SUPERSEDED' or
                            channel.connection_generation <= latest['connection_generation']):
                        raise _conflict('The reconnect generation has not advanced.')
                else:
                    raise _conflict('The session already has a lease history.')
            duration = min(self.max_duration_ms, int((expires - now).total_seconds() * 1000))
            if duration < 1000:
                raise _conflict('The authority expires too soon to grant a lease.')
            frame = decode_r4_frame(encode_r4_frame(dict(
                protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                type='lease.granted', request_id=request['request_id'], grant_id=request['grant_id'],
                lease_id='lease_' + secrets.token_hex(16), lease_serial=serial + 1,
                scope=scope, allowed_actions=actions, valid_for_ms=duration)))
            self.repo.issue(uow, request, frame, digest=digest, source_revision=source['revision'],
                            now=now.isoformat(), expires=(now + timedelta(milliseconds=duration)).isoformat())
        return frame  # The transaction committed before the caller can ACK/send.

    def applied(self, acknowledgement, *, channel: ExecutionChannel):
        frame = self._parse(acknowledgement, 'lease.applied', channel)
        scope = frame['scope']
        with self.factory.unit_of_work() as uow:
            now = _stamp(self.access.clock.now_iso())
            row = self.repo.request(uow, scope, frame['request_id'])
            latest = self.repo.latest(uow, scope)
            if (row is None or row['scope_json'] is None or row['connection_id'] != channel.connection_id or
                    row['connection_generation'] != channel.connection_generation or
                    any(frame[k] != row[k] for k in ('lease_id','lease_serial','grant_id')) or
                    json.loads(row['scope_json']) != scope or latest['lease_serial'] != row['lease_serial']):
                raise _conflict('The lease application does not match the current grant.')
            revoked = frame['application_stage'] == 'REVOKED'
            if not self.repo.current_channel(uow, channel):
                raise _conflict('The lease application came from a superseded connection.')
            if revoked:
                # A revocation ACK can only tighten state, never restore it.
                self.repo.applied(uow, scope, serial=row['lease_serial'], now=now.isoformat(), revoked=True)
                return
            _, source, actions, _ = self._authority(uow, scope, frame['grant_id'], channel, now)
            expected_stage = 'INSTALLED' if row['lease_serial'] == 1 else 'RENEWED'
            if (frame['application_stage'] != expected_stage or row['status'] not in ('ISSUED','ACTIVE') or
                    row['source_grant_revision'] != source['revision'] or
                    json.loads(row['allowed_actions_json']) != actions or _stamp(row['valid_until_server']) <= now):
                raise _conflict('The lease application is stale or revoked.')
            if row['status'] == 'ISSUED':
                if not self.repo.apply_open_bootstrap(uow, scope, row):
                    raise _conflict('The opening bootstrap changed before lease application.')
                self.repo.applied(uow, scope, serial=row['lease_serial'], now=now.isoformat())
