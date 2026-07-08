"""Local JSONL telemetry store.

This adapter mirrors the Pulse persistence shape but stays Nexus-specific:
events are append-only JSONL, acknowledgements are a separate ledger, and
state.json carries publish watermarks/token material for this install only.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


def resolve_metrics_dir(config: Any) -> Path:
    configured = getattr(config, "metrics_dir", None)
    if configured is not None:
        return Path(configured).expanduser()
    return Path(getattr(config, "home_dir")).expanduser() / "metrics"


class LocalTelemetryEventStore:
    """Filesystem implementation of TelemetryEventStore."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.events_dir = self.root / "events"
        self.sent_dir = self.root / "sent"
        self.failures_dir = self.root / "failures"
        self.exports_dir = self.root / "exports"
        self.snapshots_dir = self.root / "snapshots"
        self.events_path = self.events_dir / "events.jsonl"
        self.sent_path = self.sent_dir / "sent.jsonl"
        self.state_path = self.root / "state.json"

    def _ensure_dirs(self) -> None:
        for directory in (
            self.events_dir,
            self.sent_dir,
            self.failures_dir,
            self.exports_dir,
            self.snapshots_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _append_jsonl(path: Path, item: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(item), ensure_ascii=False, sort_keys=True))
            fh.write("\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def append_event(self, event: Mapping[str, Any]) -> None:
        self._ensure_dirs()
        self._append_jsonl(self.events_path, event)

    def iter_events(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.events_path)

    def confirmed_event_ids(self) -> set[str]:
        ids: set[str] = set()
        for row in self._read_jsonl(self.sent_path):
            for event_id in _as_list(row.get("event_ids")):
                ids.add(str(event_id))
        return ids

    def append_sent(
        self,
        *,
        batch_seq: int,
        event_ids: list[str],
        sent_at: str,
        response: Mapping[str, Any] | None = None,
    ) -> None:
        self._ensure_dirs()
        self._append_jsonl(
            self.sent_path,
            {
                "batch_seq": int(batch_seq),
                "event_ids": list(event_ids),
                "sent_at": sent_at,
                "response": dict(response or {}),
            },
        )

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def save_state(self, state: Mapping[str, Any]) -> None:
        self._ensure_dirs()
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(dict(state), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.state_path)

    def summary(self) -> dict[str, Any]:
        events = self.iter_events()
        confirmed = self.confirmed_event_ids()
        event_ids = [str(row.get("event_id")) for row in events if row.get("event_id")]
        pending_ids = [event_id for event_id in event_ids if event_id not in confirmed]
        event_types = Counter(str(row.get("event_type") or "unknown") for row in events)
        mcp_tools: Counter[str] = Counter()
        http_routes: Counter[str] = Counter()
        coordination: Counter[str] = Counter()
        lifecycle: Counter[str] = Counter()
        for row in events:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            event_type = row.get("event_type")
            if event_type == "mcp" and payload.get("tool_name"):
                mcp_tools[str(payload["tool_name"])] += 1
            elif event_type == "http" and payload.get("route_template"):
                http_routes[str(payload["route_template"])] += 1
            elif event_type == "coordination" and payload.get("coordination_type"):
                coordination[str(payload["coordination_type"])] += 1
            elif event_type == "lifecycle" and payload.get("action"):
                lifecycle[str(payload["action"])] += 1
        return {
            "event_count": len(events),
            "sent_count": len(confirmed),
            "pending_count": len(pending_ids),
            "event_type_counts": dict(sorted(event_types.items())),
            "mcp_tool_counts": dict(sorted(mcp_tools.items())),
            "http_route_template_counts": dict(sorted(http_routes.items())),
            "coordination_event_counts": dict(sorted(coordination.items())),
            "lifecycle_counts": dict(sorted(lifecycle.items())),
            "storage_dir": str(self.root),
        }

    def export_local(self) -> dict[str, Any]:
        state = dict(self.load_state())
        state.pop("install_token", None)
        state.pop("install_secret", None)
        if state.get("install_id"):
            state["install_id_redacted"] = f"{str(state.pop('install_id'))[:8]}..."
        return {
            "summary": self.summary(),
            "state": state,
            "events": self.iter_events(),
            "sent": self._read_jsonl(self.sent_path),
        }


def _as_list(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, list):
        return value
    return (value,)
