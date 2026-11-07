"""Bounded remote setup review data; never authentication or execution authority.

No persistence, discovery, transport, vault or productive service is invoked.
Canonical metadata supplied by a future authenticated caller is not proven by
its shape or digest here. Matching a review does not authorize a binding.
"""
from copy import deepcopy
import json
import re

from nexus_connector_core import CoreError
from nexus_connector_core.connection_configuration import parse_portable_connection_configuration
from ..domain.server_origin import normalize_server_origin
from .agent_creation import validate_agent_id
from .project_preset import ORIGIN
from .terminal_connection import document_revision
from ..domain.permissions import PERMISSION_REGISTRY, validate_permission_flags
from ..errors import ErrorCode, OktoNexusError


MAX_BYTES = 65536
MAX_NODES = 4096
MAX_DEPTH = 12
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z')
_HASH = re.compile(r'sha256:[0-9a-f]{64}\Z')
_REVISION = re.compile(r'[0-9a-f]{64}\Z')
_SECRET = re.compile(r'(?:nxs_|nxt4_|nxobs_|nxsept_|nxc4_)[A-Za-z0-9_-]{20,}')
_BASELINE = {'execution_revision', 'runtime_revision', 'defaults_revision', 'binding_revision', 'endpoint_revision'}
_DRAFT = {'format', 'version', 'setup_run_id', 'server_origin', 'connector_id', 'project_label',
          'agent_hint', 'workspace_hint', 'installation', 'local_consent', 'configuration', 'start_at_login'}
_SELECTION = {'server_id', 'identity', 'workspace', 'credential', 'baseline', 'native_decision_policy',
              'project_preset', 'identity_snapshot', 'remote_machine_policy', 'previous_machines'}
_GENERATED = {'executor_id', 'workspace_binding_id', 'realization_ref', 'proposal_id', 'binding_id',
              'endpoint_id', 'profile_id', 'proposal_revision', 'approved_diff_hash'}
_RECEIPT = {'setup_run_id', 'review_revision', 'server_id', 'agent_id', 'workspace_id', 'credential_epoch'}


class ContractError(OktoNexusError):
    def __init__(self, code='REMOTE_SETUP_INVALID'):
        super().__init__(ErrorCode.CONFLICT if code.endswith('REQUIRED') else ErrorCode.VALIDATION_ERROR,
            'Remote setup data could not be accepted.', {'reason': code})


def _bad(code='REMOTE_SETUP_INVALID'):
    raise ContractError(code)


def _object(value, fields):
    if type(value) is not dict or set(value) != fields:
        _bad()
    return value


def _text(value, maximum=160):
    if (type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip()
            or not value.isprintable() or _SECRET.search(value)):
        _bad()
    return value


def _identifier(value, maximum=160):
    if not _ID.fullmatch(_text(value, maximum)):
        _bad()
    return value


def _hash(value, *, prefixed=True):
    if not (_HASH if prefixed else _REVISION).fullmatch(_text(value)):
        _bad()
    return value


def _integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= (1 << 63) - 1:
        _bad()
    return value


def _bounded(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _bad()
        if type(item) is dict:
            if len(item) > 256 or any(type(key) is not str or len(key) > 160 for key in item):
                _bad()
            pending.extend((part, depth + 1) for part in item.values())
        elif type(item) is list:
            if len(item) > 256:
                _bad()
            pending.extend((part, depth + 1) for part in item)
        elif type(item) is str:
            if len(item) > 4096 or '\x00' in item or _SECRET.search(item):
                _bad()
        elif item is not None and type(item) not in (int, bool):
            _bad()
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode('utf-8')) > MAX_BYTES:
            _bad()
        return json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        _bad()


def parse_document(raw):
    """Strict JSON boundary for new files; duplicate keys/nonfinite values fail."""
    if type(raw) not in (str, bytes) or len(raw) > MAX_BYTES:
        _bad()
    try:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        if len(raw.encode('utf-8')) > MAX_BYTES:
            _bad()
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    _bad()
                value[key] = item
            return value
        return _bounded(json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: _bad()))
    except (ValueError, UnicodeError, RecursionError):
        _bad()


def _portable(value):
    if type(value) is not dict or type(value.get('version')) is not int or value['version'] != 2:
        _bad()
    if value.get('runtime_enabled') is not True or value.get('automatic_reply') is not True:
        _bad()
    try:
        return parse_portable_connection_configuration(value)
    except (CoreError, ValueError, TypeError):
        _bad()


def normalize_draft(value):
    value = _bounded(value)
    _object(value, _DRAFT)
    if value['format'] != 'okto.remote-setup-draft' or type(value['version']) is not int or value['version'] != 1:
        _bad()
    _identifier(value['setup_run_id'], 100)
    _identifier(value['connector_id'])
    _text(value['project_label'], 120)
    for name in ('agent_hint', 'workspace_hint'):
        if value[name] is not None:
            _identifier(value[name])
    if type(value['start_at_login']) is not bool:
        _bad()
    try:
        value['server_origin'] = normalize_server_origin(value['server_origin'])
    except ValueError:
        _bad()
    installation = _object(value['installation'], {'adapter_id', 'candidate_ref', 'inventory_revision'})
    _identifier(installation['adapter_id'])
    if not re.fullmatch(r'nexus-install-v1:[0-9a-f]{64}', _text(installation['candidate_ref'])):
        _bad()
    if installation['inventory_revision'] is not None:
        _hash(installation['inventory_revision'])
    consent = _object(value['local_consent'], {'local_consent_id', 'local_root_proof_digest', 'configuration_digest'})
    _identifier(consent['local_consent_id'])
    for key in ('local_root_proof_digest', 'configuration_digest'):
        if consent[key] is not None:
            _hash(consent[key])
    value['configuration'] = _portable(value['configuration'])
    if value['configuration']['adapter_id'] != installation['adapter_id']:
        _bad('REMOTE_SETUP_REVIEW_REQUIRED')
    return value


def child_request_ids(setup_run_id):
    root = _identifier(setup_run_id, 100)
    return {phase: root + '_' + phase for phase in ('register', 'realize', 'prepare', 'apply')}


def _selection(value):
    value = _bounded(value)
    _object(value, _SELECTION)
    _identifier(value['server_id'])
    identity = _object(value['identity'], {'mode', 'agent_id', 'display_name'})
    if identity['mode'] not in ('create', 'select'):
        _bad()
    try:
        validate_agent_id(_text(identity['agent_id'], 128))
    except OktoNexusError:
        _bad()
    _text(identity['display_name'], 120)
    workspace = _object(value['workspace'], {'mode', 'workspace_id', 'display_name'})
    if workspace['mode'] not in ('create', 'select'):
        _bad()
    if workspace['mode'] == 'create':
        if workspace['workspace_id'] is not None:
            _bad()
    else:
        _identifier(workspace['workspace_id'])
    _text(workspace['display_name'], 120)
    credential = _object(value['credential'], {'mode', 'expected_epoch'})
    _integer(credential['expected_epoch'])
    wrong_credential = (credential != dict(mode='issue_once', expected_epoch=0) if identity['mode'] == 'create'
                        else credential['mode'] != 'reuse_existing' or credential['expected_epoch'] < 1)
    if wrong_credential:
        _bad('REMOTE_SETUP_EXPLICIT_CREDENTIAL_REQUIRED')
    baseline = _object(value['baseline'], _BASELINE)
    for key, revision in baseline.items():
        if revision is not None or key not in ('binding_revision', 'endpoint_revision'):
            _integer(revision)
    # A first remote bootstrap cannot silently adopt/replace an existing binding.
    if baseline['binding_revision'] is not None or baseline['endpoint_revision'] is not None:
        _bad('REMOTE_SETUP_REVIEW_REQUIRED')
    policy = _object(value['native_decision_policy'], {'expected_revision', 'initialize'})
    _hash(policy['expected_revision'], prefixed=False)
    if type(policy['initialize']) is not bool or value['project_preset'] != ORIGIN:
        _bad()
    if type(value['project_preset'].get('revision')) is not int:
        _bad()
    if value['remote_machine_policy'] not in ('manual', 'auto_replace', 'deny'):
        _bad()
    normalize_previous_machines(value['previous_machines'])
    snapshot = _object(value['identity_snapshot'], {'role', 'permissions', 'defaults_hash'})
    _text(snapshot['role'], 120)
    try:
        snapshot['permissions'] = validate_permission_flags(snapshot['permissions'])
    except OktoNexusError:
        _bad()
    if (set(snapshot['permissions']) != set(PERMISSION_REGISTRY)
            or any(set(snapshot['permissions'][group]) != set(flags) for group, flags in PERMISSION_REGISTRY.items())):
        _bad()  # Snapshot must contain effective flags, never implicit defaults.
    if snapshot['defaults_hash'] is not None:
        _hash(snapshot['defaults_hash'])
    return value


def normalize_previous_machines(value):
    value = _bounded(value)
    if type(value) is not list or len(value) > 100:
        _bad()
    seen = set()
    for item in value:
        _object(item, {'binding_id', 'executor_id', 'endpoint_id', 'binding_revision',
            'endpoint_revision', 'connector_id'})
        for key in ('binding_id', 'executor_id', 'endpoint_id', 'connector_id'):
            _identifier(item[key])
        for key in ('binding_revision', 'endpoint_revision'):
            _integer(item[key], minimum=1)
        if item['binding_id'] in seen:
            _bad()
        seen.add(item['binding_id'])
    if value != sorted(value, key=lambda item: item['binding_id']):
        _bad()
    return value


def _effects(draft, selection):
    return dict(identity=selection['identity']['mode'], workspace=selection['workspace']['mode'],
        credential=selection['credential']['mode'], credential_scope='canonical_agent_identity',
        coordination_permissions=deepcopy(selection['identity_snapshot']['permissions']),
        remote_configuration=deepcopy(draft['configuration']), start_at_login=draft['start_at_login'],
        native_decision_policy=deepcopy(selection['native_decision_policy']),
        host_checks='after_confirmation', productive_turn=False,
        global_administration='never_granted_by_this_review',
        remote_machine_policy=selection['remote_machine_policy'],
        previous_machines=deepcopy(selection['previous_machines']),
        revoke_previous_machine_authority=bool(selection['previous_machines']))


def build_review(draft, selection, *, children=None):
    draft, selection = normalize_draft(draft), _selection(selection)
    children = child_request_ids(draft['setup_run_id']) if children is None else _bounded(children)
    _object(children, {'register', 'realize', 'prepare', 'apply'})
    for phase, value in children.items():
        _identifier(value)
        if not value.startswith(draft['setup_run_id'] + '_' + phase):
            _bad()
    value = dict(format='okto.remote-setup-review', version=1, draft=draft,
        draft_revision=document_revision(draft), selection=selection,
        child_requests=children, effects=_effects(draft, selection))
    return _bounded(value | {'review_revision': document_revision(value)})


def validate_review(value):
    value = _bounded(value)
    _object(value, {'format', 'version', 'draft', 'draft_revision', 'selection', 'child_requests', 'effects', 'review_revision'})
    expected = build_review(value['draft'], value['selection'], children=value['child_requests'])
    if document_revision(value) != document_revision(expected) or type(value['version']) is not int:
        _bad('REMOTE_SETUP_REVIEW_REQUIRED')
    return expected


def child_review(review, phase, canonical_request_hash, *, previous=None):
    """Pin a child's current canonical request digest to its parent review.

    This is a local comparison record, never a new wire protocol or approval.
    The authenticated caller obtains the hash from the existing normalized
    canonical request; it must not hash secret-bearing or unnormalized input.
    A changed payload with the same request ID cannot be replayed as identical.
    """
    review = validate_review(review)
    if type(phase) is not str or phase not in review['child_requests']:
        _bad()
    _hash(canonical_request_hash)
    value = dict(format='okto.remote-setup-child-review', version=1,
        setup_run_id=review['draft']['setup_run_id'], review_revision=review['review_revision'],
        phase=phase, client_intent_id=review['child_requests'][phase],
        canonical_request_hash=canonical_request_hash)
    value['child_revision'] = document_revision(value)
    if previous is not None:
        previous = _bounded(previous)
        _object(previous, set(value))
        if document_revision(previous) != document_revision(value):
            _bad('REMOTE_SETUP_REVIEW_REQUIRED')
    return value


def normalize_choices(identity, workspace):
    identity, workspace = _bounded(identity), _bounded(workspace)
    _object(identity, {'mode', 'agent_id', 'display_name'})
    _object(workspace, {'mode', 'workspace_id', 'display_name'})
    if identity['mode'] not in ('create', 'select') or workspace['mode'] not in ('create', 'select'):
        _bad()
    try:
        validate_agent_id(_text(identity['agent_id'], 128))
    except OktoNexusError:
        _bad()
    _text(identity['display_name'], 120)
    _text(workspace['display_name'], 120)
    if workspace['mode'] == 'create':
        if workspace['workspace_id'] is not None:
            _bad()
    else:
        _identifier(workspace['workspace_id'])
    return identity, workspace


def reference(value, *, optional_revision=False):
    value = _bounded(value)
    allowed = {'setup_run_id', 'review_revision'}
    if optional_revision and type(value) is dict and 'review_revision' not in value:
        value['review_revision'] = None
    _object(value, allowed)
    _identifier(value['setup_run_id'], 100)
    if value['review_revision'] is not None or not optional_revision:
        _hash(value['review_revision'], prefixed=False)
    return value
