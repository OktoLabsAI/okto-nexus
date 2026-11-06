"""Private, reference-only local coordination checkpoints; no Server data access."""
from pathlib import Path

from ...application.terminal_connection import ConnectionError, document_revision
from ...application.terminal_coordination import OPERATIONS, request_id
from .participant_files import private_directory
from .service_manager.context import atomic_json, read_json


class CoordinationFiles:
    def __init__(self, directory, scope):
        self.directory, self.scope = Path(directory), dict(scope)

    def _regular(self, path):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ConnectionError('CHECKPOINT_PATH_UNSAFE', 'Use regular coordination checkpoint files and directories.')
        return path

    def index(self):
        self._regular(self.directory)
        path = self._regular(self.directory / 'latest.json')
        if not path.exists():
            return dict(revision=1, scope=self.scope, latest={})
        value = read_json(path)
        if (value.get('revision') != 1 or value.get('scope') != self.scope or
                type(value.get('latest')) is not dict or set(value['latest']) - set(OPERATIONS)):
            raise ConnectionError('CHECKPOINT_INVALID', 'The request index belongs to another scope or is invalid.')
        for identity in value['latest'].values():
            request_id(identity)
        return value

    def path(self, operation, identity):
        if operation not in OPERATIONS:
            raise ConnectionError('REQUEST_OPERATION_REQUIRED', 'Select message_create or handoff_create.')
        request_id(identity)
        # ':' is legal in request IDs, but not in ordinary Windows filenames.
        return self._regular(self.directory / (document_revision([self.scope, operation, identity]) + '.json'))

    def load(self, operation, identity):
        self._regular(self.directory)
        path = self.path(operation, identity)
        return read_json(path) if path.exists() else None

    def save(self, value):
        private_directory(self.directory)
        index = self.index()
        operation, identity = value['operation'], value['client_request_id']
        atomic_json(self.path(operation, identity), value)
        index['latest'][operation] = identity
        # Failure of either write precedes any productive transmission.
        atomic_json(self.directory / 'latest.json', index)
