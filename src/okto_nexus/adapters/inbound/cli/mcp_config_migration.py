"""Selected MCP stdio entry migration with diff planning, backup and CAS.

Only an explicitly named entry in an explicitly named JSON file is touched.
The operator supplies an existing key through process environment; this code
does not read the Nexus database, issue a key, or scan home directories.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ....domain.keys import is_well_formed_api_key


class MigrationConflict(ValueError):
    """Input changed or an entry cannot be migrated without loss."""


@dataclass(frozen=True, slots=True)
class EntryMigrationPlan:
    path: Path
    entry_name: str
    expected_sha256: str
    replacement: bytes
    url: str
    already_applied: bool = False

    def redacted_summary(self) -> dict[str, str | bool | list[str]]:
        return {"file": str(self.path), "entry": self.entry_name,
                "expected_sha256": self.expected_sha256,
                "url": self.url,
                "already_applied": self.already_applied,
                "removed_fields": ["command", "args", "env"],
                "added_fields": ["url", "headers.Authorization"]}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise MigrationConflict("MCP config contains duplicate JSON keys.")
        result[key] = value
    return result


def _url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path.rstrip("/") != "/mcp"):
        raise MigrationConflict("URL must be a direct HTTP(S) /mcp endpoint without credentials or query.")
    return value


def plan_entry_migration(path: Path, *, entry_name: str, url: str,
                         existing_api_key: str) -> EntryMigrationPlan:
    """Plan a one-entry transform; no write or secret appears in the summary."""
    if not entry_name or not isinstance(entry_name, str):
        raise MigrationConflict("Choose one existing MCP entry by name.")
    if not is_well_formed_api_key(existing_api_key):
        raise MigrationConflict("Supply an existing nxs_ agent key through the environment.")
    url = _url(url)
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationConflict("MCP config must be a UTF-8 JSON object.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("mcpServers"), dict):
        raise MigrationConflict("MCP config must contain mcpServers object.")
    entries = document["mcpServers"]
    selected = entries.get(entry_name)
    if not isinstance(selected, dict):
        raise MigrationConflict("Selected entry does not exist.")
    if (selected.get("url") == url and
            selected.get("headers") == {"Authorization": f"Bearer {existing_api_key}"} and
            "command" not in selected and "args" not in selected):
        return EntryMigrationPlan(path, entry_name, _sha(raw), raw, url, True)
    if not isinstance(selected.get("command"), str):
        raise MigrationConflict("Selected entry is not a stdio command entry.")
    if "url" in selected or "headers" in selected:
        raise MigrationConflict("Selected entry already has HTTP fields.")
    if set(selected) - {"command", "args", "env", "disabled", "alwaysAllow"}:
        raise MigrationConflict("Selected entry has unrecognized fields; migrate it manually.")
    if "args" in selected and not isinstance(selected["args"], list):
        raise MigrationConflict("Selected args must be a list.")
    if "env" in selected and selected["env"] not in ({}, None):
        raise MigrationConflict("Selected entry has environment values; migrate it manually.")
    replacement_entry = {key: selected[key] for key in ("disabled", "alwaysAllow")
                         if key in selected}
    replacement_entry.update({"url": url,
                              "headers": {"Authorization": f"Bearer {existing_api_key}"}})
    updated = dict(document)
    updated["mcpServers"] = dict(entries)
    updated["mcpServers"][entry_name] = replacement_entry
    replacement = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return EntryMigrationPlan(path, entry_name, _sha(raw), replacement, url)


def apply_entry_migration(plan: EntryMigrationPlan) -> Path | None:
    """Apply only when the entire selected config still matches the plan."""
    path = plan.path
    original = path.read_bytes()
    if _sha(original) != plan.expected_sha256:
        raise MigrationConflict("MCP config changed after planning; regenerate the plan.")
    if plan.already_applied:
        return None
    backup = path.with_name(path.name + ".bak." + plan.expected_sha256[:12])
    if backup.exists():
        if backup.read_bytes() != original:
            raise MigrationConflict("Existing backup has different content.")
    else:
        with backup.open("xb") as fh:
            fh.write(original)
            fh.flush()
            os.fsync(fh.fileno())
    descriptor, temp_name = tempfile.mkstemp(prefix=path.name + ".r4-", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as fh:
            fh.write(plan.replacement)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temporary, path.stat().st_mode)
        if _sha(path.read_bytes()) != plan.expected_sha256:
            raise MigrationConflict("MCP config changed before replace; backup retained.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return backup
