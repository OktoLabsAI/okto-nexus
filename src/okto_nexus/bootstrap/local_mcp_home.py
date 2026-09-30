"""Host-owned, secret-free MCP homes for embedded sessions."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from nexus_connector_core import CoreError
from nexus_connector_core.harness_config import render_codex_toml_fragment
from nexus_connector_core.protocol import canonical_json


def _refuse():
    raise CoreError("PROFILE_DRIFT", "local_mcp_configuration")


def _plain(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        _refuse()


def _identity(path):
    _plain(path)
    stat = path.stat()
    return str(stat.st_dev), str(stat.st_ino)


@dataclass(frozen=True)
class SessionMCPHome:
    root: Path
    home: Path
    config: Path
    marker: bytes
    content: bytes
    identities: tuple

    def require_current(self):
        try:
            paths = (self.root, self.home, self.config.parent)
            if tuple(_identity(p) for p in paths) != self.identities:
                _refuse()
            for path, content in ((self.home / ".owner.json", self.marker), (self.config, self.content)):
                _plain(path)
                if path.stat().st_size != len(content) or path.read_bytes() != content:
                    _refuse()
        except OSError:
            _refuse()


def _write_once(path, content):
    _plain(path)
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.stat().st_size != len(content) or path.read_bytes() != content:
            _refuse()


def session_mcp_home(root, *, frame, configuration_digest, template):
    """Create once; never overwrite a foreign owner or modified config."""
    root = Path(root).absolute()
    for ancestor in (root, *root.parents):
        _plain(ancestor)
    root.mkdir(parents=True, exist_ok=True)
    _plain(root)
    ownership = dict(layout="r4-mcp-v1", scope={k: frame[k] for k in (
        "server_id", "executor_id", "binding_id", "session_id", "session_owner_generation")},
        configuration_digest=configuration_digest, capability_ref=template.capability_ref)
    marker = canonical_json(ownership)
    home = root / hashlib.sha256(marker).hexdigest()
    if home.exists():
        _plain(home)
        marker_path = home / ".owner.json"
        _plain(marker_path)
        if (not marker_path.is_file() or marker_path.stat().st_size != len(marker)
                or marker_path.read_bytes() != marker):
            _refuse()
    else:
        home.mkdir()
        _write_once(home / ".owner.json", marker)
    if template.adapter_id == "codex_app_server":
        config = home / ".codex" / "config.toml"
        _plain(config.parent)
        config.parent.mkdir(exist_ok=True)
        content = render_codex_toml_fragment(template).encode("utf-8")
    else:
        config = home / ".claude.json"
        content = json.dumps({"mcpServers": {template.entry_name: template.entry()}},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    _write_once(config, content)
    result = SessionMCPHome(root, home, config, marker, content,
                           tuple(_identity(p) for p in (root, home, config.parent)))
    result.require_current()
    return result

