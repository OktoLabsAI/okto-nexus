"""Pure, conservative projection of the qualified Herdr 0.9.5 metadata API.

Herdr counters are uint64 metadata, not Nexus report sequences. A binding is
explicit consent to one local native process incarnation, not an agent alias.
OS sampling, coherent read bracketing and durable report sequencing belong to
the adapters/application. No screen text, command line or terminal title survives
normalization here, and a path session reference is never occupant evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import ntpath
import re


HERDR_VERSION = '0.9.5'
HERDR_PROTOCOL = 22
MAX_UINT64 = (1 << 64) - 1
STATES = frozenset({'working', 'idle', 'blocked', 'done', 'unknown'})
_WRAPPERS = frozenset({
    'cmd.exe', 'powershell.exe', 'pwsh.exe', 'bash.exe', 'sh.exe', 'zsh.exe', 'fish.exe',
    'dash.exe', 'nu.exe', 'node.exe', 'nodejs.exe', 'bun.exe', 'deno.exe', 'py.exe',
    'perl.exe', 'ruby.exe', 'java.exe', 'javaw.exe', 'dotnet.exe', 'wsl.exe', 'ssh.exe',
    'conhost.exe', 'openconsole.exe', 'wt.exe', 'windowsterminal.exe', 'git-bash.exe',
    'herdr.exe', 'env.exe',
})


class HerdrObservationError(Exception):
    """Fixed diagnostic code only; never echo untrusted runtime data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__('Herdr observation unavailable: ' + code)


def _error(code):
    raise HerdrObservationError(code)


def _identifier(value, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum or not value.isprintable() or value.strip() != value:
        _error('HERDR_MALFORMED_METADATA')
    try:
        value.encode('utf-8')
    except UnicodeError:
        _error('HERDR_MALFORMED_METADATA')
    return value


def _uint(value, maximum=MAX_UINT64, *, positive=False):
    if type(value) is not int or not int(positive) <= value <= maximum:
        _error('HERDR_MALFORMED_METADATA')
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def validate_runtime(version: str, protocol: int) -> None:
    if version != HERDR_VERSION or type(version) is not str or type(protocol) is not int or protocol != HERDR_PROTOCOL:
        _error('HERDR_UNSUPPORTED_CONTRACT')


def normalize_windows_image(value: str) -> str:
    """Canonical string equality, not filesystem discovery or name inference."""
    value = _identifier(value, 32767)
    if value.startswith('\\\\?\\'):
        value = value[4:]
    drive, tail = ntpath.splitdrive(value)
    if (not re.fullmatch(r'[A-Za-z]:', drive) or not tail.startswith(('\\', '/'))
            or ':' in tail or '\x00' in value):
        _error('HERDR_LOCAL_IMAGE_REQUIRED')
    normalized = ntpath.normcase(ntpath.normpath(value))
    if not normalized.endswith('.exe'):
        _error('HERDR_NATIVE_IMAGE_REQUIRED')
    return normalized


def _session(value):
    if value is None:
        return None
    if type(value) is not dict or not {'source', 'agent', 'kind', 'value'} <= value.keys():
        _error('HERDR_MALFORMED_METADATA')
    for key in ('source', 'agent', 'kind', 'value'):
        _identifier(value[key], 1024)
    if value['kind'] not in {'id', 'path'}:
        _error('HERDR_MALFORMED_METADATA')
    if value['kind'] == 'path':
        return None
    return {key: value[key] for key in ('source', 'agent', 'kind', 'value')}


def _normalize_agent(value, *, is_agent):
    if type(value) is not dict:
        _error('HERDR_MALFORMED_METADATA')
    try:
        result = {key: _identifier(value[key]) for key in ('workspace_id', 'tab_id', 'pane_id', 'terminal_id')}
        status = value['agent_status']
        if type(status) is not str or status not in STATES:
            _error('HERDR_MALFORMED_METADATA')
        result.update(agent_status=status, revision=_uint(value['revision']), agent_session=_session(value.get('agent_session')))
        if 'focused' not in value or type(value['focused']) is not bool:
            _error('HERDR_MALFORMED_METADATA')
        result['focused'] = value['focused']
        if is_agent:
            result['state_change_seq'] = _uint(value.get('state_change_seq', 0))
            result['completion_seq'] = None if value.get('completion_seq') is None else _uint(value['completion_seq'])
        for key in ('launch_pending', 'interactive_ready', 'screen_detection_skipped'):
            if key in value and type(value[key]) is not bool:
                _error('HERDR_MALFORMED_METADATA')
        return result
    except KeyError:
        _error('HERDR_MALFORMED_METADATA')


def normalize_agent_list(agents: list) -> list[dict]:
    if type(agents) is not list or len(agents) > 4096:
        _error('HERDR_MALFORMED_METADATA')
    result = [_normalize_agent(agent, is_agent=True) for agent in agents]
    for key in ('terminal_id', 'pane_id'):
        if len({agent[key] for agent in result}) != len(result):
            _error('HERDR_AMBIGUOUS_IDENTITY')
    return result


def normalize_snapshot(snapshot: dict) -> dict:
    """Accept only an inner SessionSnapshot and discard unrelated display data."""
    if type(snapshot) is not dict:
        _error('HERDR_MALFORMED_METADATA')
    try:
        validate_runtime(snapshot['version'], snapshot['protocol'])
        for key in ('workspaces', 'tabs', 'panes', 'layouts', 'agents'):
            if type(snapshot[key]) is not list or len(snapshot[key]) > 4096:
                _error('HERDR_MALFORMED_METADATA')
        agents = normalize_agent_list(snapshot['agents'])
        panes = [_normalize_agent(pane, is_agent=False) for pane in snapshot['panes']]
        for key in ('terminal_id', 'pane_id'):
            if len({pane[key] for pane in panes}) != len(panes):
                _error('HERDR_AMBIGUOUS_IDENTITY')
        by_pane = {pane['pane_id']: pane for pane in panes}
        for agent in agents:
            pane = by_pane.get(agent['pane_id'])
            if pane is None or any(agent[key] != pane[key] for key in ('workspace_id', 'tab_id', 'terminal_id', 'agent_session')):
                _error('HERDR_INCONSISTENT_SNAPSHOT')
        return dict(version=HERDR_VERSION, protocol=HERDR_PROTOCOL, agents=agents, panes=panes)
    except KeyError:
        _error('HERDR_MALFORMED_METADATA')


def normalize_process_info(info: dict) -> dict:
    """Preserve PID facts only, including null/empty for explicit admission refusal."""
    if type(info) is not dict:
        _error('HERDR_MALFORMED_METADATA')
    try:
        pane = _identifier(info['pane_id'])
        shell = info.get('shell_pid')
        group = info.get('foreground_process_group_id')
        for pid in (shell, group):
            if pid is not None:
                _uint(pid, (1 << 32) - 1, positive=True)
        processes = info.get('foreground_processes', [])
        if type(processes) is not list or len(processes) > 256:
            _error('HERDR_MALFORMED_METADATA')
        result = []
        for process in processes:
            if type(process) is not dict:
                _error('HERDR_MALFORMED_METADATA')
            result.append(dict(pid=_uint(process['pid'], (1 << 32) - 1, positive=True)))
        return dict(pane_id=pane, shell_pid=shell, foreground_process_group_id=group, foreground_processes=result)
    except KeyError:
        _error('HERDR_MALFORMED_METADATA')


@dataclass(frozen=True, slots=True)
class WindowsProcessIdentity:
    host_id: str
    pid: int
    creation_filetime: int
    image_path: str

    def __post_init__(self):
        if type(self.host_id) is not str or not re.fullmatch(r'[0-9a-f]{64}', self.host_id):
            _error('HERDR_LOCAL_HOST_REQUIRED')
        _uint(self.pid, (1 << 32) - 1, positive=True)
        _uint(self.creation_filetime, positive=True)
        object.__setattr__(self, 'image_path', normalize_windows_image(self.image_path))


@dataclass(frozen=True, slots=True)
class HerdrBinding:
    namespace: str
    session: str
    host_id: str
    workspace_id: str
    tab_id: str
    pane_id: str
    terminal_id: str
    pid: int
    creation_filetime: int
    image_path: str
    agent_session_id_hash: str | None

    def __post_init__(self):
        for key in ('namespace', 'session', 'workspace_id', 'tab_id', 'pane_id', 'terminal_id'):
            _identifier(getattr(self, key))
        identity = WindowsProcessIdentity(self.host_id, self.pid, self.creation_filetime, self.image_path)
        object.__setattr__(self, 'image_path', identity.image_path)
        if self.agent_session_id_hash is not None and (type(self.agent_session_id_hash) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', self.agent_session_id_hash)):
            _error('HERDR_MALFORMED_BINDING')


def binding_to_dict(binding: HerdrBinding) -> dict:
    if type(binding) is not HerdrBinding:
        _error('HERDR_MALFORMED_BINDING')
    return dict(binding_version=1, herdr_version=HERDR_VERSION, protocol=HERDR_PROTOCOL, **asdict(binding))


def binding_from_dict(value: dict) -> HerdrBinding:
    fields = set(HerdrBinding.__dataclass_fields__)
    if type(value) is not dict or set(value) != fields | {'binding_version', 'herdr_version', 'protocol'}:
        _error('HERDR_MALFORMED_BINDING')
    if type(value['binding_version']) is not int or value['binding_version'] != 1:
        _error('HERDR_MALFORMED_BINDING')
    validate_runtime(value['herdr_version'], value['protocol'])
    return HerdrBinding(**{key: value[key] for key in fields})


def preview_hash(binding: HerdrBinding) -> str:
    return 'sha256:' + _hash(binding_to_dict(binding))


def bind_agent(*, namespace: str, session: str, agent: dict, process_info: dict,
               identity: WindowsProcessIdentity, approved_image: str) -> HerdrBinding:
    # Normalized data remains detached dicts. Revalidate the identity-bearing
    # fields so callers cannot turn a malformed checkpoint into authority.
    if type(agent) is not dict:
        _error('HERDR_MALFORMED_METADATA')
    for key in ('workspace_id', 'tab_id', 'pane_id', 'terminal_id'):
        if key not in agent:
            _error('HERDR_MALFORMED_METADATA')
        _identifier(agent[key])
    info = normalize_process_info(process_info)
    processes = info['foreground_processes']
    if (type(identity) is not WindowsProcessIdentity or len(processes) != 1
            or info['shell_pid'] is None or info['foreground_process_group_id'] is None
            or processes[0]['pid'] == info['shell_pid'] or processes[0]['pid'] != info['foreground_process_group_id']
            or processes[0]['pid'] != identity.pid or info['pane_id'] != agent['pane_id']):
        _error('HERDR_OCCUPANT_UNPROVEN')
    image = normalize_windows_image(approved_image)
    if image != identity.image_path:
        _error('HERDR_PROCESS_IMAGE_CHANGED')
    basename = ntpath.basename(image)
    if basename in _WRAPPERS or re.fullmatch(r'python(?:\d+(?:\.\d+)*)?w?\.exe', basename):
        _error('HERDR_WRAPPER_UNSUPPORTED')
    session_ref = _session(agent.get('agent_session'))
    return HerdrBinding(namespace, session, identity.host_id, agent['workspace_id'], agent['tab_id'], agent['pane_id'],
                        agent['terminal_id'], identity.pid, identity.creation_filetime, image,
                        _hash(session_ref) if session_ref is not None else None)


@dataclass(frozen=True, slots=True)
class HerdrObservation:
    binding_hash: str
    state: str
    evidence: str
    revision: int
    state_change_seq: int
    completion_seq: int | None
    last_completion_seq: int
    completion_ref: str | None

    def to_dict(self):
        return asdict(self)


def observation_from_dict(value: dict) -> HerdrObservation:
    if type(value) is not dict or set(value) != set(HerdrObservation.__dataclass_fields__):
        _error('HERDR_MALFORMED_CHECKPOINT')
    if (type(value['binding_hash']) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', value['binding_hash'])
            or type(value['state']) is not str or value['state'] not in {'working', 'idle', 'blocked', 'unknown'}
            or value['evidence'] != 'inferred'):
        _error('HERDR_MALFORMED_CHECKPOINT')
    for key in ('revision', 'state_change_seq', 'last_completion_seq'):
        _uint(value[key])
    if value['completion_seq'] is not None:
        _uint(value['completion_seq'])
        if value['last_completion_seq'] < value['completion_seq']:
            _error('HERDR_MALFORMED_CHECKPOINT')
    if value['completion_ref'] is not None:
        expected_ref = 'herdr:' + value['binding_hash'].removeprefix('sha256:') + ':' + str(value['completion_seq'])
        if (value['completion_ref'] != expected_ref or value['state'] != 'idle'
                or value['completion_seq'] is None or value['completion_seq'] <= 0
                or value['completion_seq'] != value['state_change_seq']):
            _error('HERDR_MALFORMED_CHECKPOINT')
    return HerdrObservation(**value)


def reconcile_binding(binding: HerdrBinding, *, agent: dict | None, process_info: dict,
                      identity: WindowsProcessIdentity, previous: HerdrObservation | None = None) -> HerdrObservation:
    if type(binding) is not HerdrBinding:
        _error('HERDR_MALFORMED_BINDING')
    if agent is None:
        _error('HERDR_BOUND_OCCUPANT_MISSING')
    current = bind_agent(namespace=binding.namespace, session=binding.session, agent=agent,
                         process_info=process_info, identity=identity, approved_image=binding.image_path)
    if current != binding:
        _error('HERDR_BINDING_CHANGED')
    status = agent.get('agent_status')
    if type(status) is not str or status not in STATES:
        _error('HERDR_MALFORMED_METADATA')
    revision = _uint(agent.get('revision'))
    state_seq = _uint(agent.get('state_change_seq', 0))
    completion = None if agent.get('completion_seq') is None else _uint(agent['completion_seq'])
    binding_hash = preview_hash(binding)
    baseline = 0
    completion_ref = None
    state = 'idle' if status == 'done' else status
    if previous is not None:
        if type(previous) is not HerdrObservation:
            _error('HERDR_MALFORMED_CHECKPOINT')
        previous = observation_from_dict(previous.to_dict())
        if previous.binding_hash != binding_hash:
            _error('HERDR_BINDING_CHANGED')
        baseline = previous.last_completion_seq
        if (revision < previous.revision or state_seq < previous.state_change_seq
                or completion is not None and completion < baseline):
            _error('HERDR_COUNTER_REGRESSED')
        if state_seq > 0 and state_seq == previous.state_change_seq and state != previous.state:
            _error('HERDR_INCONSISTENT_STATE_SEQUENCE')
        if (status in {'idle', 'done'} and completion is not None and completion == state_seq
                and completion > baseline and state_seq > previous.state_change_seq):
            completion_ref = 'herdr:' + binding_hash.removeprefix('sha256:') + ':' + str(completion)
        elif (state == 'idle' and completion is not None and completion > 0 and completion == state_seq
                and completion == previous.completion_seq and previous.completion_ref is not None):
            completion_ref = previous.completion_ref
    # First snapshot establishes a baseline, even if it says done. Omission
    # never resets the remembered completion or manufactures a fresh one.
    return HerdrObservation(binding_hash, state, 'inferred', revision, state_seq,
                            completion, max(baseline, completion or 0), completion_ref)
