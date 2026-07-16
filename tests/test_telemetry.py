from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.outbound.telemetry.http_sender import NexusTelemetryHttpSink
from okto_nexus.adapters.outbound.telemetry.local_store import LocalTelemetryEventStore
from okto_nexus.application.telemetry.schema import (
    EVENT_HTTP,
    EVENT_MCP,
    TelemetrySchemaError,
    normalize_payload,
)
from okto_nexus.application.telemetry.service import TelemetryService
from okto_nexus.config import load_config
from okto_nexus.errors import OktoNexusError
from okto_nexus.testing import FakeServer


class FakeClock:
    def __init__(self) -> None:
        self.epoch = 1_700_000_000.0

    def now_iso(self) -> str:
        return "2026-07-08T00:00:00.000000Z"

    def now_epoch(self) -> float:
        return self.epoch


def test_metrics_config_parses_env_and_cli(tmp_path):
    config = load_config(
        {
            "OKTO_NEXUS_METRICS_MODE": "local_only",
            "OKTO_NEXUS_METRICS_DIR": str(tmp_path / "metrics-env"),
            "OKTO_NEXUS_METRICS_BEACON_URL": "https://example.test",
            "OKTO_NEXUS_METRICS_PUBLISH_INTERVAL_SECONDS": "120",
        },
        [
            "--metrics-mode",
            "anonymous_beacon",
            "--metrics-dir",
            str(tmp_path / "metrics-cli"),
        ],
    )
    assert config.metrics_mode == "anonymous_beacon"
    assert config.metrics_dir == tmp_path / "metrics-cli"
    assert config.metrics_beacon_url == "https://example.test"
    assert config.metrics_publish_interval_seconds == 120


def test_metrics_config_rejects_invalid_mode():
    with pytest.raises(OktoNexusError):
        load_config({"OKTO_NEXUS_METRICS_MODE": "full_payload_upload"})


def test_telemetry_schema_rejects_sensitive_values_but_allows_tool_name():
    assert normalize_payload(
        EVENT_MCP,
        {"tool_name": "message_create", "status": "ok", "duration_ms": 5},
    ) == {"tool_name": "message_create", "status": "ok", "duration_ms": 5}

    with pytest.raises(TelemetrySchemaError) as exc:
        normalize_payload(EVENT_MCP, {"tool_name": "x", "error_code": "a@b.com"})
    assert exc.value.code == "SENSITIVE_PAYLOAD_VALUE"

    with pytest.raises(TelemetrySchemaError) as exc:
        normalize_payload(EVENT_HTTP, {"route_template": "C:\\Users\\jpamb\\file.txt"})
    assert exc.value.code == "SENSITIVE_PAYLOAD_VALUE"


def test_service_disabled_never_writes(tmp_path):
    store = LocalTelemetryEventStore(tmp_path / "metrics")
    service = TelemetryService(
        config=SimpleNamespace(metrics_mode="disabled"),
        store=store,
        clock=FakeClock(),
    )

    assert service.record_event(EVENT_MCP, {"tool_name": "tag_list", "status": "ok"})[
        "written"
    ] is False
    assert store.iter_events() == []


def test_local_store_summary_counts_pending_events(tmp_path):
    store = LocalTelemetryEventStore(tmp_path / "metrics")
    service = TelemetryService(
        config=SimpleNamespace(metrics_mode="local_only"),
        store=store,
        clock=FakeClock(),
    )

    result = service.record_event(
        EVENT_MCP,
        {"tool_name": "message_create", "status": "ok", "duration_ms": 12},
    )

    assert result == {"written": True, "event_type": EVENT_MCP}
    summary = service.summary()
    assert summary["event_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["mcp_tool_counts"] == {"message_create": 1}
    assert summary["mode"] == "local_only"


class FakeHttpSink(NexusTelemetryHttpSink):
    def __init__(self, *, config: Any, clock: FakeClock) -> None:
        super().__init__(config=config, clock=clock, app_version="test")
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    def _post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        self.calls.append((path, payload, headers))
        if path == "/v1/handshake":
            return {
                "install_token": "secret",
                "token_ttl_seconds": 3600,
                "accepted_schema_version": "1.0.0",
            }
        return {"accepted": True, "firehose_record_id": "rec-1"}


def test_http_sink_handshakes_signs_and_marks_pending_events_sent(tmp_path):
    clock = FakeClock()
    config = SimpleNamespace(
        metrics_mode="anonymous_beacon",
        metrics_beacon_url="https://example.test",
    )
    store = LocalTelemetryEventStore(tmp_path / "metrics")
    service = TelemetryService(config=config, store=store, clock=clock)
    service.record_event(
        EVENT_MCP, {"tool_name": "agent_whoami", "status": "ok", "duration_ms": 1}
    )
    sink = FakeHttpSink(config=config, clock=clock)

    result = sink.send_pending(store)

    assert result == {"sent": True, "count": 1, "batch_seq": 1}
    assert [call[0] for call in sink.calls] == ["/v1/handshake", "/v1/usage"]
    usage_payload = sink.calls[1][1]
    usage_headers = sink.calls[1][2]
    assert usage_payload["metrics"]["mcp_tool_counts"] == {"agent_whoami": 1}
    assert usage_payload["events"] == []
    assert usage_headers["x-okto-batch-seq"] == "1"
    assert usage_headers["x-okto-signature"]
    assert store.summary()["pending_count"] == 0


def test_mcp_tool_registration_records_local_metric(tmp_path):
    deps = bootstrap(
        {
            "OKTO_NEXUS_HOME": str(tmp_path / "home"),
            "OKTO_NEXUS_METRICS_MODE": "local_only",
        },
        [],
    )
    server = FakeServer()
    register_tools(server, deps)

    result = server.tools["tag_list"]()

    assert result["ok"] is True
    summary = deps.telemetry.summary()
    assert summary["mcp_tool_counts"]["tag_list"] == 1
