"""Trusted local registration, not arbitrary import strings supplied by clients."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..domain.endpoints import ADAPTER_CONTRACT_VERSION, EndpointCapabilities, adapter_identifier
from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    kind: str
    substrate: str | None
    protocol: str
    factory: Callable[..., Any]
    config_validator: Callable[[dict], None]
    capabilities: EndpointCapabilities
    legacy_capabilities: Any
    contract_version: int = ADAPTER_CONTRACT_VERSION
    supported_platforms: tuple[str, ...] = ()
    native_versions_tested: tuple[str, ...] = ()
    configuration_schema: dict = field(default_factory=dict)
    input_schema: dict = field(default_factory=dict)
    compatibility_probe: Callable[..., Any] | None = None


class AdapterRegistry:
    def __init__(self):
        self._entries: dict[str, AdapterDescriptor] = {}

    def register(self, descriptor: AdapterDescriptor) -> None:
        adapter_identifier(descriptor.adapter_id)
        adapter_identifier(descriptor.kind)
        if descriptor.contract_version != ADAPTER_CONTRACT_VERSION:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported adapter contract version.", {})
        if descriptor.adapter_id in self._entries or any(
            (d.kind, d.substrate) == (descriptor.kind, descriptor.substrate) for d in self._entries.values()
        ):
            raise OktoNexusError(ErrorCode.CONFLICT, "Adapter already registered.", {})
        self._entries[descriptor.adapter_id] = descriptor

    def resolve(self, kind: str, substrate: str | None = None) -> AdapterDescriptor:
        matches = [d for d in self._entries.values() if d.kind == kind and d.substrate == substrate]
        if len(matches) != 1:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Adapter is not registered for this connection.", {})
        return matches[0]

    def get(self, adapter_id: str) -> AdapterDescriptor:
        if adapter_id not in self._entries:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "Adapter is not registered.", {})
        return self._entries[adapter_id]

    def descriptors(self) -> tuple[AdapterDescriptor, ...]:
        return tuple(self._entries[k] for k in sorted(self._entries))
