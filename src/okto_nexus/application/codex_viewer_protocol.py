"""Scoped protocol presented to the reviewed Codex 0.170.0 terminal."""

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue

from ..domain.session_interaction import validate_input_text
from ..errors import OktoNexusError
from .codex_presenter_requests import (
    _exact_uuid,
    codex_history_page,
    codex_thread_presentation,
)

HISTORY_METHODS = ('thread/turns/list', 'thread/items/list')
THREAD_METHODS = ('thread/read', 'thread/resume')
_TURN_START_NULL_FIELDS = frozenset({
    'disabledPluginIds', 'parentTurnId', 'rootTurnId', 'toolOutput', 'responsesapiClientMetadata',
    'responsesapiClientMetadataPatch', 'additionalContext', 'environments', 'approvalsReviewer',
    'sandboxPolicy', 'permissions', 'serviceTierForTurn', 'summary', 'personality', 'outputSchema',
    'collaborationMode', 'multiAgentMode', 'cyberAccessProgram',
})


def _plain_next_turn(params, context):
    """Strip only the unchanged defaults sent by the reviewed frontend."""
    defaults = {'cwd': context.cwd, 'model': context.model, 'effort': context.reasoning_effort,
                'approvalPolicy': context.approval_policy, 'serviceTier': 'default',
                'runtimeWorkspaceRoots': [], 'turnTrigger': 'user'}
    identity = params.get('clientUserMessageId')
    inputs = params.get('input')
    if (params.get('threadId') != context.thread_id or not _exact_uuid(identity, identity)
            or params.keys() - _TURN_START_NULL_FIELDS - defaults.keys() - {'threadId', 'input', 'clientUserMessageId'}
            or any(params.get(key) is not None for key in _TURN_START_NULL_FIELDS)
            or any(params.get(key) not in (None, value) for key, value in defaults.items())
            or not isinstance(inputs, list) or len(inputs) != 1):
        raise ValueError('The viewer changed the selected thread or launch options.')
    return 'codex_' + identity, _plain_text(inputs[0])


def _plain_text(item):
    if (not isinstance(item, dict) or item.keys() - {'type', 'text', 'text_elements'}
            or item.get('type') != 'text' or type(item.get('text')) is not str
            or item.get('text_elements', []) != [] or item['text'].lstrip().startswith(('/', '!'))):
        raise ValueError('Send a plain-text message with no attachments or commands.')
    return validate_input_text(item['text'])


def _plain_steer(params, context):
    metadata = {'responsesapiClientMetadata', 'responsesapiClientMetadataPatch', 'additionalContext'}
    identity, target, content = (params.get(key) for key in ('clientUserMessageId', 'expectedTurnId', 'input'))
    if (params.get('threadId') != context.thread_id or not _exact_uuid(identity, identity)
            or not _exact_uuid(target, target) or any(params.get(key) is not None for key in metadata)
            or params.keys() - metadata - {'threadId', 'expectedTurnId', 'clientUserMessageId', 'input'}
            or not isinstance(content, list) or len(content) != 1):
        raise ValueError('Reorientation requires the exact active turn and a plain-text message.')
    return 'codex_steer_' + identity, target, _plain_text(content[0])


class CodexInputStatus(Exception):
    """Safe operator feedback from the scoped viewer protocol."""


@dataclass(frozen=True, slots=True)
class CodexPendingInput:
    input_id: str | None
    message: str
    steer_target: str | None = None


def _printable(value: str) -> str:
    if not value.isprintable():
        raise ValueError('Invalid viewer metadata text.')
    return value


def _absolute_path(value: str) -> str:
    if not (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()):
        raise ValueError('The viewer needs an absolute working directory.')
    return value


ShortText = Annotated[str, Field(min_length=1, max_length=256), AfterValidator(_printable)]
EpochSeconds = Annotated[int, Field(ge=0, lt=2**53)]


class CodexViewerContext(BaseModel):
    """Exact facts from an authorized owner, already projected for the viewer."""

    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)

    thread_id: ShortText
    session_id: ShortText
    cwd: Annotated[str, Field(min_length=1, max_length=4096), AfterValidator(_printable),
                   AfterValidator(_absolute_path)]
    model: ShortText
    model_provider: ShortText
    status: Literal['idle', 'active', 'systemError']
    created_at: EpochSeconds
    updated_at: EpochSeconds
    ephemeral: bool
    cli_version: ShortText
    source: Literal['cli', 'vscode', 'exec', 'appServer', 'unknown']
    approval_policy: Literal['untrusted', 'on-request', 'never'] | dict[Literal['granular'], dict[str, bool]]
    approvals_reviewer: Literal['user', 'auto_review', 'guardian_subagent']
    sandbox: dict[Literal['type', 'networkAccess', 'excludeSlashTmp', 'excludeTmpdirEnvVar', 'writableRoots'], JsonValue]
    reasoning_effort: Literal['none', 'minimal', 'low', 'medium', 'high', 'xhigh']

    def thread(self):
        status = {'type': self.status}
        if self.status == 'active':
            status['activeFlags'] = []
        return {
            'id': self.thread_id, 'sessionId': self.session_id, 'projectId': None, 'path': None,
            'preview': '', 'ephemeral': self.ephemeral, 'modelProvider': self.model_provider,
            'createdAt': self.created_at, 'updatedAt': self.updated_at, 'status': status,
            'cwd': self.cwd, 'cliVersion': self.cli_version, 'source': self.source, 'turns': [],
        }

    def view(self, thread):
        return {
            'thread': thread, 'cwd': self.cwd, 'model': self.model, 'modelProvider': self.model_provider,
            'approvalPolicy': self.approval_policy, 'approvalsReviewer': self.approvals_reviewer,
            'sandbox': self.sandbox, 'reasoningEffort': self.reasoning_effort,
        }


class CodexViewerProtocol:
    """Terminate native RPC locally and project reviewed reads and input."""

    def __init__(self, *, context: CodexViewerContext, read_page, viewer_home: str, platform_os: str,
                 send_next_turn=None, steer=None):
        self.context = context
        self._read_page = read_page
        self._viewer_home = viewer_home
        self._platform_os = platform_os
        self._send_next_turn = send_next_turn
        self._steer = steer
        self._initialized = False
        self.detached = False
        self.following = False
        self.pending_delivery = None
        self._steer_message_ids = set()

    def handle(self, request):
        if (not isinstance(request, dict) or request.keys() - {'jsonrpc', 'id', 'method', 'params'}
                or request.get('jsonrpc', '2.0') != '2.0' or not isinstance(request.get('method'), str)):
            return self._error(None, -32600, 'Invalid viewer request.')
        request_id = request.get('id')
        if 'id' not in request:
            return None
        if (type(request_id) not in (int, str)
                or type(request_id) is int and not -2**53 < request_id < 2**53
                or type(request_id) is str and (len(request_id) > 160 or not request_id.isprintable())):
            return self._error(None, -32600, 'Invalid viewer request ID.')
        method = request['method']
        params = request.get('params')
        params = {} if params is None else params
        if not isinstance(params, dict):
            return self._error(request_id, -32602, 'Invalid viewer parameters.')
        try:
            result = self._dispatch(method, params)
        except CodexInputStatus as status:
            return self._error(request_id, -32000, str(status))
        except OktoNexusError:
            return self._error(request_id, -32602, 'The request is outside the selected viewer scope.')
        if isinstance(result, CodexPendingInput):
            self.pending_delivery = (request_id, result)
            return None
        if result is None:
            return self._error(request_id, -32601, 'This method is unavailable in the local viewer.')
        return {'id': request_id, 'result': result}

    def _dispatch(self, method, params):
        if method == 'initialize' and not self._initialized:
            self._initialized = True
            return {'userAgent': 'nexus-codex-presenter/1', 'codexHome': self._viewer_home,
                    'platformFamily': 'windows' if self._platform_os == 'windows' else 'unix',
                    'platformOs': self._platform_os}
        if not self._initialized or self.detached:
            return None
        if self._send_next_turn is not None:
            if method == 'turn/start' and self.following:
                if self.pending_delivery is not None:
                    raise CodexInputStatus('Check the preceding message in the Nexus session queue.')
                try:
                    intent, text = _plain_next_turn(params, self.context)
                except ValueError as error:
                    raise CodexInputStatus(str(error)) from None
                if params['clientUserMessageId'] in self._steer_message_ids:
                    raise CodexInputStatus('This message was reviewed for reorientation. Send a new message explicitly to queue it.')
                return self._send_next_turn(thread_id=self.context.thread_id, intent=intent, text=text)
            if method == 'turn/steer':
                if not self.following or self._steer is None or self.pending_delivery is not None:
                    raise CodexInputStatus('Review and confirm reorientation in Nexus for the selected turn.')
                try:
                    intent, turn_id, text = _plain_steer(params, self.context)
                except ValueError as error:
                    raise CodexInputStatus(str(error)) from None
                if len(self._steer_message_ids) >= 4096:
                    raise CodexInputStatus('Reopen this presentation to review another reorientation.')
                self._steer_message_ids.add(params['clientUserMessageId'])
                return self._steer(thread_id=self.context.thread_id, turn_id=turn_id, intent=intent, text=text)
        if method in THREAD_METHODS:
            request = codex_thread_presentation(method=method, params=params, native_thread_id=self.context.thread_id)
            thread = self.context.thread()
            if request.include_turns:
                turns = self._inline_turns()
                if turns is None:
                    return None
                thread['turns'] = turns
                self.following = True
            return {'thread': thread} if request.kind == 'read' else self.context.view(thread)
        if method in HISTORY_METHODS:
            codex_history_page(method=method, params=params, native_thread_id=self.context.thread_id)
            return self._read_page(method=method, params=params)
        if method == 'thread/unsubscribe' and params == {'threadId': self.context.thread_id}:
            self.detached = True
            return {'status': 'unsubscribed'}
        if method == 'model/list' and params.get('cursor') is None:
            effort = self.context.reasoning_effort
            model = self.context.model
            return {'data': [{'id': model, 'model': model, 'displayName': model, 'description': '',
                'defaultReasoningEffort': effort,
                'supportedReasoningEfforts': [{'reasoningEffort': effort, 'description': ''}],
                'hidden': False, 'isDefault': True}], 'nextCursor': None}
        # The viewer reads these catalogs during startup. They describe the
        # read-only presentation and never expose the engine's account or tools.
        return {
            'account/read': {'account': None, 'requiresOpenaiAuth': False},
            'config/read': {'config': {}, 'origins': {}},
            'configRequirements/read': {'requirements': None},
            'account/bedrock/checkGovCloudRequirements': {'isGovCloud': False, 'shouldWarn': False},
            'collaborationMode/list': {'data': []},
            'hooks/list': {'data': []},
            'skills/list': {'data': []},
        }.get(method)

    def _inline_turns(self):
        """Assemble a small complete page pair for Codex's inline history lookup."""
        params = {'threadId': self.context.thread_id, 'sortDirection': 'asc'}
        turns = self._read_page(method=HISTORY_METHODS[0], params=params | {'limit': 20, 'itemsView': 'notLoaded'})
        if (turns.get('nextCursor') is not None or not isinstance(turns.get('data'), list)
                or len(turns['data']) > 20):
            return None
        items = self._read_page(method=HISTORY_METHODS[1], params=params | {'limit': 100})
        if (items.get('nextCursor') is not None or not isinstance(items.get('data'), list)
                or len(items['data']) > 100):
            return None
        by_turn = {}
        for turn in turns['data']:
            if not isinstance(turn, dict) or not isinstance(turn.get('id'), str) or turn['id'] in by_turn:
                return None
            by_turn[turn['id']] = []
        for item in items['data']:
            if (not isinstance(item, dict) or not isinstance(item.get('turnId'), str)
                    or item['turnId'] not in by_turn or not isinstance(item.get('item'), dict)):
                return None
            by_turn[item['turnId']].append(item['item'])
        return [{**turn, 'items': by_turn[turn['id']], 'itemsView': 'summary'} for turn in turns['data']]

    @staticmethod
    def _error(request_id, code, message):
        return {'id': request_id, 'error': {'code': code, 'message': message}}
