"""HTTP/HMAC telemetry publisher."""

from __future__ import annotations

import hashlib
import hmac
import json
import platform
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ....application.ports import Clock
from ....application.telemetry.ports import TelemetryEventStore
from ....application.telemetry.schema import CURRENT_SCHEMA_VERSION


class NexusTelemetryHttpSink:
    """Publish pending local telemetry to the anonymous beacon endpoint."""

    def __init__(
        self,
        *,
        config: Any,
        clock: Clock,
        app_version: str = "dev",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._config = config
        self._clock = clock
        self._app_version = app_version
        self._timeout_seconds = timeout_seconds

    def send_pending(self, store: TelemetryEventStore) -> dict[str, Any]:
        events = store.iter_events()
        confirmed = store.confirmed_event_ids()
        pending = [
            event
            for event in events
            if event.get("event_id") and str(event["event_id"]) not in confirmed
        ]
        if not pending:
            return {"sent": False, "reason": "no_pending", "count": 0}

        state = store.load_state()
        install_id = str(state.get("install_id") or uuid.uuid4().hex)
        state["install_id"] = install_id
        token = self._ensure_token(store, state)
        batch_seq = int(state.get("next_batch_seq") or 1)
        payload = self._build_payload(
            install_id=install_id,
            batch_seq=batch_seq,
            pending=pending,
        )
        timestamp = str(int(self._clock.now_epoch()))
        nonce = secrets.token_hex(16)
        body = _canonical_json(payload)
        signature = _signature(
            token,
            f"{timestamp}.{nonce}.{batch_seq}.{body}",
        )
        try:
            response = self._post_json(
                "/v1/usage",
                payload,
                headers={
                    "x-okto-signature": signature,
                    "x-okto-timestamp": timestamp,
                    "x-okto-nonce": nonce,
                    "x-okto-batch-seq": str(batch_seq),
                },
            )
        except Exception:
            self._record_failure(
                store, state, reason_code="usage_publish_failed", http_status=None
            )
            raise
        if not bool(response.get("accepted", True)):
            self._record_failure(
                store,
                state,
                reason_code=str(response.get("reason") or "usage_rejected"),
                http_status=None,
            )
            return {"sent": False, "reason": "usage_rejected"}
        event_ids = [str(event["event_id"]) for event in pending]
        sent_at = self._clock.now_iso()
        store.append_sent(
            batch_seq=batch_seq,
            event_ids=event_ids,
            sent_at=sent_at,
            response=response,
        )
        state["next_batch_seq"] = batch_seq + 1
        state["failure_state"] = {
            "status": "ok",
            "last_success_at": sent_at,
            "retry_count": 0,
        }
        store.save_state(state)
        return {"sent": True, "count": len(event_ids), "batch_seq": batch_seq}

    def _ensure_token(self, store: TelemetryEventStore, state: dict[str, Any]) -> str:
        token = str(state.get("install_token") or "")
        expires_at = float(state.get("install_token_expires_at") or 0)
        if token and expires_at > self._clock.now_epoch() + 60:
            return token
        install_id = str(state["install_id"])
        try:
            response = self._post_json(
                "/v1/handshake",
                {
                    "install_id": install_id,
                    "runtime": {
                        "name": "okto-nexus",
                        "platform": platform.system().lower() or "unknown",
                    },
                    "app_version": self._app_version,
                    "platform_arch": platform.machine(),
                    "schema_version": CURRENT_SCHEMA_VERSION,
                },
                headers={},
            )
        except Exception:
            self._record_failure(
                store, state, reason_code="handshake_failed", http_status=None
            )
            raise
        token = str(response.get("install_token") or "")
        if not token:
            self._record_failure(
                store, state, reason_code="handshake_missing_token", http_status=None
            )
            raise RuntimeError("telemetry handshake did not return install_token")
        ttl = int(response.get("token_ttl_seconds") or 2_592_000)
        state["install_token"] = token
        state["install_token_expires_at"] = self._clock.now_epoch() + ttl
        state["accepted_schema_version"] = response.get("accepted_schema_version")
        state["limits"] = response.get("limits") if isinstance(response.get("limits"), dict) else {}
        store.save_state(state)
        return token

    def _build_payload(
        self,
        *,
        install_id: str,
        batch_seq: int,
        pending: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "install_id": install_id,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "runtime": "okto-nexus",
            "app_version": self._app_version,
            "batch_seq": batch_seq,
            "bucket_start": _bucket_start(self._clock.now_iso()),
            "bucket_duration_seconds": 3600,
            "era": "post_fix",
            "semantics": "delta",
            "trust_state": "trusted_delta",
            "metrics": _aggregate_metrics(pending),
            "events": [],
            "event_count": len(pending),
        }

    def _post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        url = urljoin(str(getattr(self._config, "metrics_beacon_url")).rstrip("/") + "/", path.lstrip("/"))
        body = _canonical_json(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "user-agent": f"okto-nexus/{self._app_version}",
                **dict(headers),
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"telemetry_http_{exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("telemetry_network_error") from exc
        if not raw:
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    def _record_failure(
        self,
        store: TelemetryEventStore,
        state: dict[str, Any],
        *,
        reason_code: str,
        http_status: int | None,
    ) -> None:
        previous = state.get("failure_state") if isinstance(state, dict) else {}
        previous = previous if isinstance(previous, dict) else {}
        retry_count = int(previous.get("retry_count") or 0) + 1
        state["failure_state"] = {
            "status": "degraded",
            "last_failure_at": self._clock.now_iso(),
            "reason_code": reason_code,
            "http_status": http_status,
            "retry_count": retry_count,
        }
        store.save_state(state)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _signature(secret: str, value: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def _bucket_start(value: str) -> str:
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.now(timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _aggregate_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "event_type_counts": {},
        "cli_counts": {},
        "mcp_tool_counts": {},
        "http_route_template_counts": {},
        "coordination_event_counts": {},
        "lifecycle_counts": {},
        "status_counts": {},
        "error_code_counts": {},
        "error_class_counts": {},
        "duration_ms_buckets": {"lt_100": 0, "100_999": 0, "1000_plus": 0},
    }
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        _inc(metrics["event_type_counts"], event_type)
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("status"):
            _inc(metrics["status_counts"], str(payload["status"]))
        if payload.get("error_code"):
            _inc(metrics["error_code_counts"], str(payload["error_code"]))
        if payload.get("error_class"):
            _inc(metrics["error_class_counts"], str(payload["error_class"]))
        if event_type == "cli" and payload.get("command"):
            _inc(metrics["cli_counts"], str(payload["command"]))
        elif event_type == "mcp" and payload.get("tool_name"):
            _inc(metrics["mcp_tool_counts"], str(payload["tool_name"]))
        elif event_type == "http" and payload.get("route_template"):
            _inc(metrics["http_route_template_counts"], str(payload["route_template"]))
        elif event_type == "coordination" and payload.get("coordination_type"):
            _inc(metrics["coordination_event_counts"], str(payload["coordination_type"]))
        elif event_type == "lifecycle" and payload.get("action"):
            _inc(metrics["lifecycle_counts"], str(payload["action"]))
        duration = payload.get("duration_ms")
        if isinstance(duration, int):
            if duration < 100:
                metrics["duration_ms_buckets"]["lt_100"] += 1
            elif duration < 1000:
                metrics["duration_ms_buckets"]["100_999"] += 1
            else:
                metrics["duration_ms_buckets"]["1000_plus"] += 1
    return metrics


def _inc(bucket: dict[str, int], key: str) -> None:
    bucket[key] = int(bucket.get(key, 0)) + 1
