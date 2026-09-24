"""Trusted descriptor probe plus approved profile restrictions, outside SQLite."""
from dataclasses import asdict, replace
from functools import partial

from ....application.runtime_requirements import validate_effective_capability
from ....domain.endpoints import EndpointCapabilities
from ....domain.runtime_commands import RuntimeCommandNotSent
from ....errors import ErrorCode, OktoNexusError
from .secret_redaction import BackendSecretRedactor


class QualifiedConnector:
    def __init__(self, connector, *, descriptor, disabled=(), hitl_enabled=False, redactor=None):
        self.connector, self.descriptor = connector, descriptor
        self.capabilities = replace(connector.capabilities,
            multiplexes_sessions=connector.capabilities.multiplexes_sessions and descriptor.capabilities.multiplexing
            and "multiplexing" not in disabled)
        self.disabled, self.hitl_enabled = tuple(disabled), hitl_enabled
        self.redactor = redactor or BackendSecretRedactor()

    def __getattr__(self, name):
        value = getattr(self.connector, name)
        return partial(self.redactor.call, value) if callable(value) else value

    def events(self):
        return self.redactor.events(self.redactor.call(self.connector.events))

    def events_for_session(self, session_id):
        scoped = getattr(self.connector, "events_for_session", None)
        events = self.redactor.call(scoped, session_id) if callable(scoped) else self.redactor.call(self.connector.events)
        return self.redactor.events(events)

    def start(self, *, owning_agent_id):
        session = self.redactor.call(self.connector.start, owning_agent_id=owning_agent_id)
        session = replace(session, metadata=self.redactor.clean(session.metadata),
                          compatibility_report=self.redactor.clean(session.compatibility_report))
        probe = self.descriptor.compatibility_probe
        observed = probe(dict(session.compatibility_report)) if probe else EndpointCapabilities()
        if not isinstance(observed, EndpointCapabilities):
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Adapter compatibility probe returned an invalid contract.", {})
        effective = observed.restrict(self.descriptor.capabilities)
        restrictions = {name: None if name == "steer_timing" else False for name in self.disabled}
        if not self.hitl_enabled:
            restrictions["approvals"] = False
        effective = replace(effective, **restrictions)
        if not effective.events or not effective.correlated_results:
            effective = replace(effective, managed_work=False)
        report = dict(session.compatibility_report,
            effective_capability_contract=1, effective_capabilities=asdict(effective),
            effective_capability_basis="trusted_adapter_probe_and_profile" if probe else "unverified")
        report.pop("backend_secret_redaction", None)
        if self.redactor.active:
            report["backend_secret_redaction"] = {"version": self.redactor.version,
                "raw_text": "withheld", "normalized_output": "bounded_stream_then_terminal_flush"}
        return replace(session, compatibility_report=report)

    def send(self, session, command):
        capability = {"send_turn": "conversation", "steer": "steer_timing", "interrupt": "interrupt"}.get(command.verb)
        if command.verb == "send_turn" and command.payload.get("envelope", {}).get("intent") == "handoff_execute":
            capability = "managed_work"
        if capability:
            try:
                validate_effective_capability(session.compatibility_report, capability)
            except OktoNexusError as exc:
                raise RuntimeCommandNotSent(str(exc)) from exc
        return self.redactor.call(self.connector.send, session, command)
