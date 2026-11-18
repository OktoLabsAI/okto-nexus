"""Reduce observed Codex 0.170.0 thread reads to exact presenter requests."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from ..errors import ErrorCode, OktoNexusError

# The viewer emits these fields with null values during a normal exact resume.
# Any supplied override belongs to a separate engine operation.
_RESUME_OVERRIDES = frozenset({
    'approvalPolicy', 'approvalsReviewer', 'baseInstructions', 'config', 'cwd',
    'developerInstructions', 'history', 'initialTurnsPage', 'model', 'modelProvider',
    'path', 'permissions', 'personality', 'runtimeWorkspaceRoots', 'sandbox',
})
_RESUME_FIELDS = _RESUME_OVERRIDES | {'threadId', 'excludeTurns'}
_READ_FIELDS = frozenset({'threadId', 'includeTurns'})


@dataclass(frozen=True, slots=True)
class CodexThreadPresentation:
    kind: Literal['read', 'initialize_view']
    include_turns: bool


def codex_thread_presentation(*, method: str, params: object, native_thread_id: str) -> CodexThreadPresentation:
    """Resolve a bounded read intent. The caller owns the target and response.

    No native method, parameters or provider selection are carried onward.
    `initialize_view` builds a response from an existing thread and has
    no relationship to the upstream engine's `thread/resume` operation.
    """
    if method not in ('thread/read', 'thread/resume'):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presenter method is unavailable.', {})
    if not isinstance(params, dict) or not _exact_uuid(native_thread_id, params.get('threadId')):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The exact presentation thread is unavailable.', {})
    if method == 'thread/read':
        include = params.get('includeTurns', False)
        if params.keys() - _READ_FIELDS or type(include) is not bool:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'The presentation read is invalid.', {})
        return CodexThreadPresentation('read', include)
    exclude = params.get('excludeTurns', True)
    if (params.keys() - _RESUME_FIELDS or type(exclude) is not bool
            or any(params.get(field) is not None for field in _RESUME_OVERRIDES)):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The presenter cannot change the thread context.', {})
    return CodexThreadPresentation('initialize_view', not exclude)


def _exact_uuid(expected: str, requested: object) -> bool:
    if type(expected) is not str or type(requested) is not str or expected != requested or len(expected) != 36:
        return False
    try:
        return str(UUID(expected)) == expected
    except ValueError:
        return False
