"""Private cooperation attempts, separate from ordinary coordination requests."""
from pathlib import Path

from ...application.terminal_connection import ConnectionError, document_revision
from ...application.terminal_coordination import request_id
from .coordination_files import CoordinationFiles
from .participant_files import _check_private, private_directory
from .service_manager.context import atomic_json, read_json


class CooperationFiles:
    def __init__(self, directory, scope, profile_binding):
        self.directory = Path(directory)
        self.scope, self.profile_binding = dict(scope), profile_binding
        self.selected = None

    @staticmethod
    def _regular(path):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ConnectionError('CHECKPOINT_PATH_UNSAFE', 'Use regular private cooperation checkpoint paths.')
        return path

    def _base(self):
        for path in (self.directory.parent, self.directory):
            self._regular(path)
        if self.directory.exists():
            _check_private(self.directory)

    def _attempt(self, identity):
        self._base()
        request_id(identity)
        parent = self._regular(self.directory / 'attempts')
        path = self._regular(parent / document_revision([self.scope, identity]))
        if path.exists():
            _check_private(path)
        return path

    def load(self, identity=None):
        self._base()
        if identity is None:
            index_path = self._regular(self.directory / 'latest.json')
            if not index_path.exists():
                attempts = self._regular(self.directory / 'attempts')
                if attempts.exists() and any(attempts.iterdir()):
                    raise ConnectionError('SMOKE_INDEX_MISSING',
                        'Cooperation attempts exist but their index is missing. Select --attempt explicitly; do not replace uncertain work.')
                return None
            index = read_json(index_path)
            if (set(index) != {'revision', 'scope', 'profile_binding', 'smoke_id'} or
                    index.get('revision') != 1 or index.get('scope') != self.scope or
                    index.get('profile_binding') != self.profile_binding):
                raise ConnectionError('SMOKE_SCOPE_CHANGED', 'The cooperation index belongs to a different participant setup.')
            identity = index['smoke_id']
        path = self._regular(self._attempt(identity) / 'smoke.json')
        if not path.is_file():
            raise ConnectionError('SMOKE_CHECKPOINT_MISSING', 'The selected cooperation attempt is missing. Preserve its ID for review.')
        value = read_json(path)
        if (value.get('smoke_id') != identity or value.get('scope') != self.scope or
                value.get('profile_binding') != self.profile_binding):
            raise ConnectionError('SMOKE_SCOPE_CHANGED', 'The cooperation attempt belongs to a different participant setup.')
        self.selected = identity
        return value

    def save(self, value):
        if value.get('scope') != self.scope or value.get('profile_binding') != self.profile_binding:
            raise ConnectionError('SMOKE_SCOPE_CHANGED', 'The cooperation attempt cannot change its participant setup.')
        identity = request_id(value['smoke_id'])
        directory = self._attempt(identity)
        path = self._regular(directory / 'smoke.json')
        first_write = not path.exists()
        private_directory(self.directory)
        private_directory(directory)
        self.selected = identity
        atomic_json(path, value)
        # Only a new review selects the latest attempt. Observing an older
        # attempt cannot replace a concurrently selected newer one.
        if first_write:
            atomic_json(self._regular(self.directory / 'latest.json'), dict(
                revision=1, scope=self.scope, profile_binding=self.profile_binding, smoke_id=identity))

    def guard_path(self):
        if self.selected is None:
            raise ConnectionError('SMOKE_REVIEW_REQUIRED', 'Review the directed exchange before continuing.')
        return self._regular(self._attempt(self.selected) / 'smoke.guard')

    def _requests(self):
        if self.selected is None:
            raise ConnectionError('SMOKE_REVIEW_REQUIRED', 'Review the directed exchange before continuing.')
        return CoordinationFiles(self._attempt(self.selected) / 'requests', self.scope)

    def load_request(self, operation, identity):
        return self._requests().load(operation, identity)

    def save_request(self, value):
        return self._requests().save(value)
