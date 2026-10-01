"""Inert interpretation of legacy compatibility reports; live R4 catalog belongs to Core."""
from ....domain.endpoints import EndpointCapabilities


CONVERSATION_VERSIONS = {"codex": {"0.156.1"}, "claude_code": {"2.1.280", "2.1.281"}, "pi": {"0.85.1"}}


def qualified_capabilities(kind, substrate, report):
    if substrate == "attach":
        supported = (report.get("transport_contract") == "cc_socks_peer_1" and
                     type(report.get("peer_protocol")) is int and report["peer_protocol"] == 1)
        return EndpointCapabilities(conversation=supported)
    version = report.get("native_version")
    supported = version in CONVERSATION_VERSIONS.get(kind, ())
    controls = report.get("compatible_controls", ()) if supported else ()
    return EndpointCapabilities(conversation=supported, managed_work=supported,
        events=supported, correlated_results=supported,
        multiplexing=supported and kind == "codex",
        steer_timing=("NEXT_TURN_BOUNDARY" if kind == "pi" else "IMMEDIATE") if "steer" in controls else None,
        interrupt="interrupt" in controls, interrupt_requires_settle=kind == "pi",
        observes_stop=kind in {"pi", "codex", "claude_code"},
        approvals=supported and bool(report.get("compatible_native_requests")))
