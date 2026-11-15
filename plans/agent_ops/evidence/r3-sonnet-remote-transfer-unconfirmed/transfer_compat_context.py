"""Additive FILETIME compatibility; original gates retained."""
from pathlib import Path
from transfer_context import TransferContext as OriginalContext
from request_context import require, read_json, sha, pin
HERE=Path(__file__).resolve().parent
BASE_FREEZE_SHA='6bd4a176b1606ff3aa173e771b9c9a06eb3210dfe167701bdacbc2a060f71dc6'
def verify_compat():
    base=HERE/'transfer-freeze.json'
    require(sha(base)==BASE_FREEZE_SHA,'BASE_TRANSFER_FREEZE_CHANGED')
    for value in read_json(base)['files'].values():pin(value)
    manifest=read_json(HERE/'transfer-compat-manifest.json')
    require(manifest['base_freeze_sha256']==BASE_FREEZE_SHA,'COMPAT_BASE_CHANGED')
    for value in manifest['runtime'].values():pin(value)
    return manifest
class TransferContext(OriginalContext):
    def __init__(self,path,expected):
        verify_compat()
        super().__init__(path,expected)
    def require_connector_ready(self):
        from connector_lifecycle_compat import current_ready
        return current_ready(self)
