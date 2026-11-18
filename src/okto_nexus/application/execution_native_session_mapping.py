"""Read a managed native identity from the canonical opening and its receipt."""

import json
from dataclasses import asdict, dataclass

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.session_interaction import InputScope
from .execution_inventory_revalidation import selection


@dataclass(frozen=True, slots=True)
class NativeLaunchBuild:
    version: str
    platform: str
    architecture: str
    content_fingerprint: str
    build_identity: str | None
    qualification: str


def native_launch_build(snapshot: dict, opening: dict) -> dict | None:
    """Capture validated managed launch evidence at canonical admission."""
    if opening.get('mode') != 'managed' or opening.get('inventory_revision') != snapshot['inventory_revision']:
        return None
    selected = selection(snapshot, opening['adapter_id'], opening['candidate_ref'])
    if selected is None:
        return None
    build = _launch_build(selected['evidence'])
    return asdict(build) if build is not None else None


def _launch_build(evidence: dict) -> NativeLaunchBuild | None:
    fields = ('version', 'platform', 'architecture', 'content_fingerprint', 'qualification')
    values = {name: evidence.get(name) for name in fields}
    if not all(type(value) is str and value for value in values.values()):
        return None
    build_identity = evidence.get('build_identity')
    if build_identity is not None and (type(build_identity) is not str or not build_identity):
        return None
    return NativeLaunchBuild(**values, build_identity=build_identity)


@dataclass(frozen=True, slots=True)
class ManagedNativeSession:
    scope: InputScope
    opening_operation_id: str
    adapter_id: str
    native_session_id: str
    stream_epoch: str | None
    launch_candidate_ref: str
    launch_inventory_revision: str
    launch_profile_revision: int
    launch_build: NativeLaunchBuild | None
    receipt_connection_id: str | None
    receipt_connection_generation: int | None


def read_managed_native_session(uow, scope: InputScope) -> ManagedNativeSession | None:
    """Resolve retained identity only. Process ownership and access need separate proof."""
    row = uow.connection.execute("""
        SELECT s.stream_epoch, s.native_launch_build_json, p.operation_id, p.semantic_payload,
               r.native_id, r.source_connection_id, r.source_connection_generation
        FROM execution_sessions s
        JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id
          AND p.operation_id=s.open_operation_id AND p.session_id=s.session_id
        JOIN execution_receipts r ON r.server_id=p.server_id AND r.executor_id=p.executor_id
          AND r.operation_id=p.operation_id AND r.receipt_revision=(
            SELECT MAX(prior.receipt_revision) FROM execution_receipts prior
            WHERE prior.server_id=p.server_id AND prior.executor_id=p.executor_id AND prior.operation_id=p.operation_id)
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
          AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
          AND s.workspace_binding_id=:workspace_binding_id AND s.owner_generation=:owner_generation
          AND p.action='runtime.open' AND p.subject_agent_id=:agent_id AND p.binding_id=:binding_id
          AND p.workspace_id=:workspace_id AND p.workspace_binding_id=:workspace_binding_id
          AND json_extract(p.expected_revisions_json,'$.session_owner_generation')=:owner_generation
          AND r.intent_hash=p.intent_hash AND r.stage IN ('SUBMITTED','SUCCEEDED')
    """, _scope_params(scope)).fetchone()
    if row is None:
        return None
    native_id = row['native_id']
    if (not isinstance(native_id, str) or not 1 <= len(native_id) <= 160
            or not native_id.isprintable() or 'REDACTED' in native_id):
        return None
    opening = json.loads(row['semantic_payload'])
    payload = opening.get('payload')
    if opening.get('action') != 'runtime.open' or not isinstance(payload, dict) or payload.get('mode') != 'managed':
        return None
    adapter, candidate, inventory = (payload.get(name) for name in ('adapter_id', 'candidate_ref', 'inventory_revision'))
    revision = payload.get('profile_revision')
    if not all(isinstance(value, str) and value for value in (adapter, candidate, inventory)):
        return None
    if type(revision) is not int or revision < 1:
        return None
    build = _launch_build(json.loads(row['native_launch_build_json'])) if row['native_launch_build_json'] else None
    return ManagedNativeSession(scope, row['operation_id'], adapter, native_id, row['stream_epoch'],
        candidate, inventory, revision, build, row['source_connection_id'], row['source_connection_generation'])
