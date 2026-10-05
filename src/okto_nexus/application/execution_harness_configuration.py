"""Read an authenticated Core observation bound to this endpoint and revision."""
import hashlib
import json

from nexus_connector_core import discover_harness_configuration, CoreError
from nexus_connector_core.protocol import canonical_json


def read_harness_configuration(conn, *, endpoint_id, adapter_id, candidate_ref=None, version=None):
    fallback = discover_harness_configuration(adapter_id, candidate_ref=candidate_ref, version=version)
    # Never reuse another agent/account's catalogue. A changed configuration,
    # credential epoch, binding or installation requires a new observation.
    rows = conn.execute(
        "SELECT e.payload_json,b.candidate_ref FROM execution_event_ingress e "
        "JOIN execution_sessions s USING(server_id,executor_id,session_id) "
        "JOIN execution_bindings b USING(server_id,executor_id,binding_id) "
        "JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
        "AND o.operation_id=s.open_operation_id "
        "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
        "JOIN execution_agent_revisions r ON r.server_id=b.server_id AND r.agent_id=ep.agent_id "
        "WHERE b.endpoint_id=? AND e.event_type='lifecycle' "
        "AND json_extract(e.payload_json,'$.native_type')='core/harness_configuration' "
        "AND json_extract(o.expected_revisions_json,'$.credential_epoch')=r.credential_epoch "
        "AND json_extract(o.expected_revisions_json,'$.configuration_revision')=r.configuration_revision "
        "AND e.received_at>=strftime('%Y-%m-%dT%H:%M:%fZ','now','-30 minutes') "
        "ORDER BY e.received_at DESC LIMIT 1", (endpoint_id,)).fetchall()
    for row in rows:
        try:
            value = json.loads(row['payload_json'])['payload']['harness_configuration']
            revision = value.pop('schema_revision')
            if revision != 'sha256:' + hashlib.sha256(canonical_json(value)).hexdigest():
                continue
            value['schema_revision'] = revision
            if (value['schema_version'] != 1 or value['adapter_id'] != adapter_id or
                    value['candidate_ref'] != row['candidate_ref'] or
                    (candidate_ref is not None and value['candidate_ref'] != candidate_ref)):
                continue
            # Reconstruct the public projection from bounded native-shaped
            # inputs, retaining Core-owned labels and supported parameters.
            models = value['models']
            if adapter_id == 'codex_app_server':
                native = {'data':[{'model':m['id'], 'supportedReasoningEfforts':[
                    {'reasoningEffort':level} for level in m['efforts']],
                    'defaultReasoningEffort':m['default_effort']} for m in models]}
                constraints = value.get('constraints', {})
                requirements = {source: constraints[target] for source,target in [
                    ('allowedApprovalPolicies','approval_policy'), ('allowedSandboxModes','sandbox')]
                    if target in constraints}
            elif adapter_id == 'pi_rpc':
                native = {'models':[{'id':m['id'],'provider':m['provider']} for m in models]}
                requirements = None
            elif adapter_id == 'claude_stream':
                return discover_harness_configuration(adapter_id, version=value['version'],
                    candidate_ref=value['candidate_ref'], native_parameters=[
                        {k:p[k] for k in ('name','type','values')} for p in value['parameters']
                        if p['availability'] == 'observed'])
            else:
                continue
            return discover_harness_configuration(adapter_id, version=value['version'],
                candidate_ref=value['candidate_ref'], native_models=native, requirements=requirements)
        except (KeyError, TypeError, ValueError, CoreError):
            continue
    return fallback
