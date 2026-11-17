"""Pure Quick Connect product contracts; no discovery or execution authority.

Invalid construction raises ValueError. Inbound adapters translate that error to
their existing validation response. Validation messages never echo input values.
Omitted optional wire members stay omitted, especially for legacy requests.
"""
from dataclasses import asdict, dataclass
import re
from typing import Literal


ProjectNameSource = Literal['explicit', 'existing_nexus', 'git_origin', 'git_worktree', 'directory', 'manual']
ProjectNameStatus = Literal['selected', 'suggested', 'saved', 'unconfirmed']
DiscoveryStatus = Literal['not_needed', 'discovered', 'fallback', 'saved', 'not_run_plan', 'unconfirmed']
DiscoveryReason = Literal[
    'explicit_name', 'existing_nexus', 'saved_selection', 'git_origin', 'git_worktree',
    'directory_fallback', 'git_unavailable', 'not_a_repository', 'origin_missing',
    'origin_invalid', 'origin_ambiguous', 'git_timeout', 'git_output_limit',
    'git_config_unavailable', 'git_cleanup_unconfirmed', 'dubious_ownership', 'unsafe_git_executable',
    'unsupported_git_transport', 'invalid_project_name', 'not_run_plan', 'not_needed', 'unconfirmed',
]
OutcomeStatus = Literal[
    'connected', 'planned', 'selection_required', 'conflict', 'pending',
    'cancelled', 'unknown', 'failed', 'configured_shortcut_pending',
]
ConnectIdStatus = Literal['proposed', 'reserved', 'bound']
ConnectOperation = Literal['created', 'reused', 'associated_existing']
ExecutionLocation = Literal['local', 'remote']
CwdSource = Literal['cwd', 'explicit_project', 'existing_nexus', 'manual', 'saved', 'remote']

_PUBLIC_ID = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}', re.ASCII)


def normalize_connect_id(value: str) -> str:
    """Normalize only the public connection name, never a canonical identity."""
    if type(value) is not str or _PUBLIC_ID.fullmatch(value) is None:
        raise ValueError('Harness ID must be 1–64 ASCII letters, digits, underscores or hyphens, starting with a letter.')
    return value.lower()


def _text(value, field, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not str or not value.strip() or not value.isprintable():
        raise ValueError(f'Invalid {field}.')


def _enum(value, allowed, field, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not str or value not in allowed:
        raise ValueError(f'Invalid {field}.')


_NAME_SOURCES = ('explicit', 'existing_nexus', 'git_origin', 'git_worktree', 'directory', 'manual')
_REASONS = (
    'explicit_name', 'existing_nexus', 'saved_selection', 'git_origin', 'git_worktree',
    'directory_fallback', 'git_unavailable', 'not_a_repository', 'origin_missing',
    'origin_invalid', 'origin_ambiguous', 'git_timeout', 'git_output_limit',
    'git_config_unavailable', 'git_cleanup_unconfirmed', 'dubious_ownership', 'unsafe_git_executable',
    'unsupported_git_transport', 'invalid_project_name', 'not_run_plan', 'not_needed', 'unconfirmed',
)


@dataclass(frozen=True, slots=True)
class ConnectionIntent:
    requested_harness: str | None
    project_name: str | None
    connect_id: str | None
    invocation_cwd: str
    project_root: str
    root_explicit: bool
    new_connection: bool = False

    def __post_init__(self):
        _text(self.requested_harness, 'requested harness', optional=True)
        _text(self.project_name, 'project name', optional=True)
        _text(self.invocation_cwd, 'invocation directory')
        _text(self.project_root, 'project root')
        if type(self.root_explicit) is not bool or type(self.new_connection) is not bool:
            raise ValueError('Root and connection intent flags must be booleans.')
        if self.connect_id is not None:
            object.__setattr__(self, 'connect_id', normalize_connect_id(self.connect_id))


@dataclass(frozen=True, slots=True)
class ProjectNameChoice:
    name: str
    source: ProjectNameSource
    status: ProjectNameStatus
    reason: DiscoveryReason

    def __post_init__(self):
        _text(self.name, 'project name')
        _enum(self.source, _NAME_SOURCES, 'project name source')
        _enum(self.status, ('selected', 'suggested', 'saved', 'unconfirmed'), 'project name status')
        _enum(self.reason, _REASONS, 'discovery reason')


@dataclass(frozen=True, slots=True)
class NameDiscovery:
    status: DiscoveryStatus
    reason: DiscoveryReason

    def __post_init__(self):
        _enum(self.status, ('not_needed', 'discovered', 'fallback', 'saved', 'not_run_plan', 'unconfirmed'), 'discovery status')
        _enum(self.reason, _REASONS, 'discovery reason')


@dataclass(frozen=True, slots=True)
class CwdResolution:
    invocation_cwd: str
    project_root: str | None
    root_explicit: bool
    source: CwdSource

    def __post_init__(self):
        _text(self.invocation_cwd, 'invocation directory')
        _text(self.project_root, 'project root', optional=True)
        if type(self.root_explicit) is not bool:
            raise ValueError('Root intent must be a boolean.')
        _enum(self.source, ('cwd', 'explicit_project', 'existing_nexus', 'manual', 'saved', 'remote'), 'root source')


@dataclass(frozen=True, slots=True)
class CanonicalConnectionReference:
    """An exact catalog reference, not proof of permission or runtime readiness."""
    server_id: str
    executor_id: str
    workspace_id: str
    binding_id: str
    workspace_binding_id: str
    agent_id: str
    endpoint_id: str

    def __post_init__(self):
        for field, value in asdict(self).items():
            _text(value, field)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuickConnectOutcome:
    status: OutcomeStatus
    version: Literal[1] = 1
    connect_id: str | None = None
    proposed_connect_id: str | None = None
    connect_id_status: ConnectIdStatus | None = None
    operation: ConnectOperation | None = None
    harness: str | None = None
    project_name: str | None = None
    project_name_source: ProjectNameSource | None = None
    name_discovery: NameDiscovery | None = None
    execution_location: ExecutionLocation | None = None
    project_root: str | None = None
    cwd_resolution: CwdResolution | None = None
    resume_argv: tuple[str, ...] = ()
    canonical_reference: CanonicalConnectionReference | None = None

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError('Unsupported Quick Connect outcome version.')
        _enum(self.status, ('connected', 'planned', 'selection_required', 'conflict', 'pending',
            'cancelled', 'unknown', 'failed', 'configured_shortcut_pending'), 'outcome status')
        _enum(self.connect_id_status, ('proposed', 'reserved', 'bound'), 'Harness ID status', optional=True)
        _enum(self.operation, ('created', 'reused', 'associated_existing'), 'connection operation', optional=True)
        _enum(self.execution_location, ('local', 'remote'), 'execution location', optional=True)
        _enum(self.project_name_source, _NAME_SOURCES, 'project name source', optional=True)
        for field in ('harness', 'project_name', 'project_root'):
            _text(getattr(self, field), field, optional=True)
        for field in ('connect_id', 'proposed_connect_id'):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, normalize_connect_id(value))
        for field, expected in (('name_discovery', NameDiscovery), ('cwd_resolution', CwdResolution),
                                ('canonical_reference', CanonicalConnectionReference)):
            value = getattr(self, field)
            if value is not None and type(value) is not expected:
                raise ValueError(f'Invalid {field}.')
        if type(self.resume_argv) is not tuple:
            raise ValueError('Resume arguments must be an immutable argument vector.')
        for value in self.resume_argv:
            _text(value, 'resume argument')
        if self.connect_id_status == 'bound':
            if self.connect_id is None or self.canonical_reference is None or self.proposed_connect_id is not None:
                raise ValueError('A bound Harness ID requires its exact canonical reference and no proposed ID.')
        elif self.connect_id is not None:
            raise ValueError('An unbound Harness ID belongs in proposed_connect_id.')
        if self.connect_id_status in ('proposed', 'reserved') and self.proposed_connect_id is None:
            raise ValueError('A proposed or reserved Harness ID requires proposed_connect_id.')
        if self.status == 'connected' and (self.connect_id_status != 'bound' or self.operation is None or
                self.harness is None or self.project_name is None):
            raise ValueError('Connected requires a bound Harness ID, exact reference and identified operation.')
        if self.status == 'planned' and (self.connect_id_status == 'bound' or self.connect_id is not None):
            raise ValueError('A plan cannot declare a bound Harness ID.')
        if self.cwd_resolution is not None and self.cwd_resolution.project_root != self.project_root:
            raise ValueError('Root resolution does not match the outcome root.')

    def to_dict(self) -> dict:
        """Return fresh JSON-compatible data, without synthesizing omitted members."""
        value = {key: item for key, item in asdict(self).items() if item is not None}
        value['resume_argv'] = list(self.resume_argv)
        return value
