"""Local-directory adapter for the ArtifactStore port.

Every artifact is materialised under::

    <nexus-home>/artifacts/<workspace>/<agent>/<artifact-id>/

The directory contains the payload plus a small ``manifest.json``.  The
application receives only a relative storage path, keeping the adapter root an
infrastructure concern and allowing a future object-store adapter to implement
the same port.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from ....domain.artifacts import StoredArtifactPayload
from ....errors import ErrorCode, OktoNexusError

_MANIFEST = "manifest.json"
_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")
_EXTENSIONS = {
    "json": ".json",
    "markdown": ".md",
    "text": ".txt",
    "html": ".html",
}
_MEDIA_TYPES = {
    "json": "application/json",
    "markdown": "text/markdown",
    "text": "text/plain",
    "html": "text/html",
}


def _segment(value: str, *, fallback: str) -> str:
    raw = value.strip()
    cleaned = _SAFE_SEGMENT.sub("_", raw).strip("._")
    if not cleaned:
        cleaned = fallback
    if cleaned != raw:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned[:80]}-{digest}"
    return cleaned[:96]


def _payload_filename(
    *, artifact_type: str, name: str | None, source_path: str | None
) -> str:
    raw = Path(source_path).name if source_path else Path(name or "artifact").name
    cleaned = _SAFE_SEGMENT.sub("_", raw).strip("._") or "artifact"
    if cleaned.lower() == _MANIFEST:
        cleaned = "artifact-payload"
    extension = _EXTENSIONS.get(artifact_type, "")
    if extension and not Path(cleaned).suffix:
        cleaned += extension
    return cleaned[:160]


class LocalArtifactStore:
    """Store artifact payloads below one adapter-owned local root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def put(
        self,
        *,
        workspace_id: str,
        agent_id: str | None,
        artifact_id: str,
        artifact_type: str,
        storage_kind: str,
        name: str | None,
        content: str | bytes | None,
        source_path: str | None,
        metadata: dict[str, Any],
        created_at: str,
    ) -> StoredArtifactPayload:
        workspace_segment = _segment(workspace_id, fallback="workspace")
        agent_segment = _segment(agent_id or "anonymous", fallback="anonymous")
        artifact_segment = _segment(artifact_id, fallback="artifact")
        parent = self.root / workspace_segment / agent_segment
        final_dir = parent / artifact_segment
        filename = _payload_filename(
            artifact_type=artifact_type, name=name, source_path=source_path
        )
        relative_payload = Path(
            workspace_segment, agent_segment, artifact_segment, filename
        ).as_posix()

        if final_dir.exists():
            existing = self.describe(relative_payload)
            return existing

        parent.mkdir(parents=True, exist_ok=True)
        temp_dir = parent / f".{artifact_segment}.tmp-{uuid4().hex}"
        try:
            temp_dir.mkdir()
            temp_payload = temp_dir / filename
            if content is not None:
                data = (
                    content if isinstance(content, bytes) else content.encode("utf-8")
                )
                temp_payload.write_bytes(data)
            else:
                source = Path(source_path or "")
                if not source.is_file():
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        "artifact path must reference an existing file.",
                        {"path": source_path},
                    )
                shutil.copyfile(source, temp_payload)

            size_bytes = temp_payload.stat().st_size
            media_type = (
                _MEDIA_TYPES.get(artifact_type)
                or mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )
            manifest = {
                "schema_version": 1,
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "storage_kind": storage_kind,
                "name": name,
                "filename": filename,
                "media_type": media_type,
                "size_bytes": size_bytes,
                "source_path": source_path,
                "metadata": metadata,
                "created_at": created_at,
                "storage_path": relative_payload,
            }
            (temp_dir / _MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_dir, final_dir)
        except OktoNexusError:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise
        except (OSError, TypeError, ValueError) as exc:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to persist artifact payload.",
                {"artifact_id": artifact_id, "reason": str(exc)},
            ) from exc

        return self.describe(relative_payload)

    def describe(self, storage_path: str) -> StoredArtifactPayload:
        payload = self._resolve(storage_path)
        manifest_path = payload.parent / _MANIFEST
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("manifest is not an object")
            metadata = raw.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            return StoredArtifactPayload(
                storage_path=str(raw.get("storage_path") or storage_path),
                storage_kind=str(raw["storage_kind"]),
                filename=str(raw["filename"]),
                media_type=str(raw.get("media_type") or "application/octet-stream"),
                size_bytes=int(raw["size_bytes"]),
                metadata=metadata,
                source_path=(
                    str(raw["source_path"])
                    if isinstance(raw.get("source_path"), str)
                    else None
                ),
                local_path=str(payload),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Artifact manifest is missing or invalid.",
                {"storage_path": storage_path, "reason": str(exc)},
            ) from exc

    def read_text(self, storage_path: str) -> str:
        try:
            return self._resolve(storage_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to read artifact text payload.",
                {"storage_path": storage_path, "reason": str(exc)},
            ) from exc

    def read_bytes(self, storage_path: str) -> bytes:
        try:
            return self._resolve(storage_path).read_bytes()
        except OSError as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to read artifact payload.",
                {"storage_path": storage_path, "reason": str(exc)},
            ) from exc

    def delete(self, storage_path: str) -> None:
        payload = self._resolve(storage_path)
        artifact_dir = payload.parent
        if not (artifact_dir / _MANIFEST).is_file():
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Refusing to remove an artifact directory without a manifest.",
                {"storage_path": storage_path},
            )
        try:
            shutil.rmtree(artifact_dir)
        except OSError as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to remove artifact payload after rollback.",
                {"storage_path": storage_path, "reason": str(exc)},
            ) from exc

    def _resolve(self, storage_path: str) -> Path:
        candidate = (self.root / storage_path).resolve()
        try:
            contained = candidate.is_relative_to(self.root)
        except AttributeError:  # pragma: no cover - Python 3.11+ is required
            contained = os.path.commonpath([self.root, candidate]) == str(self.root)
        if not contained:
            raise OktoNexusError(
                ErrorCode.PATH_OUTSIDE_WORKSPACE,
                "Artifact storage path escapes the configured root.",
                {"storage_path": storage_path},
            )
        return candidate
