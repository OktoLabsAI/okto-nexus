"""Scoped read-only protocol presented to the Codex 0.170.0 terminal."""

from dataclasses import dataclass

from ..errors import OktoNexusError
from .codex_presenter_requests import codex_history_page, codex_thread_presentation

HISTORY_METHODS = ('thread/turns/list', 'thread/items/list')
THREAD_METHODS = ('thread/read', 'thread/resume')
EFFORTS = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh')


@dataclass(frozen=True, slots=True)
class CodexViewerContext:
    """Exact facts from an authorized owner, already projected for the viewer."""

    thread_id: str
    session_id: str
    cwd: str
    model: str
    model_provider: str
    status: str
    created_at: int
    updated_at: int
    ephemeral: bool
    cli_version: str
    source: str
    approval_policy: str | dict
    approvals_reviewer: str
    sandbox: dict
    reasoning_effort: str

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
    """Terminates native RPC locally; only reviewed page requests cross the link."""

    def __init__(self, *, context: CodexViewerContext, read_page, viewer_home: str, platform_os: str):
        self.context = context
        self._read_page = read_page
        self._viewer_home = viewer_home
        self._platform_os = platform_os
        self._initialized = False
        self.detached = False

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
        except OktoNexusError:
            return self._error(request_id, -32602, 'The request is outside the selected viewer scope.')
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
        if method in THREAD_METHODS:
            request = codex_thread_presentation(method=method, params=params, native_thread_id=self.context.thread_id)
            thread = self.context.thread()
            if request.include_turns:
                turns = self._inline_turns()
                if turns is None:
                    return None
                thread['turns'] = turns
            return {'thread': thread} if request.kind == 'read' else self.context.view(thread)
        if method in HISTORY_METHODS:
            codex_history_page(method=method, params=params, native_thread_id=self.context.thread_id)
            return self._read_page(method=method, params=params)
        if method == 'thread/unsubscribe' and params == {'threadId': self.context.thread_id}:
            self.detached = True
            return {'status': 'unsubscribed'}
        if method == 'model/list' and params.get('cursor') is None:
            effort = self.context.reasoning_effort
            if effort not in EFFORTS:
                return None
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
