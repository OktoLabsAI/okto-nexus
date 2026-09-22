# P02 contract v1

Logical mappings:

- AgentEndpoint → domain.endpoints.AgentEndpoint (exact workspace; disabled
  by default; stable identity/revision; selection and response policies).
- RequestContext / ExecutionGrant → domain.runtime_context. Trusted request
  construction remains at the authentication boundary. Grant persistence and
  enforcement belong to P03/P04, not claims made by this dataclass.
- DeliveryEnvelope / DispatchResult → domain.delivery. Intent is structured,
  content remains untrusted, managed execution requires claim correlation,
  transport write does not imply acceptance, timeout does not permit retry.
- AdapterRegistry / AdapterDescriptor → application.adapter_registry. Trusted
  local factories only; duplicate registrations and incompatible versions fail.
- Versioned protocol façade → outbound.harness.envelope.EnvelopeConnector.
  Canonical JSON/provenance is encoded to native text/content at the edge.
  Text delimiters do not create an instruction hierarchy or sandbox.

Production tools/REST resolve the same registry from the composition root.
The four built-ins remain available; existing connector factory injection is
retained as compatibility for protocol tests. Domain validates adapter ID syntax,
not a closed product list. Legacy HARNESS_KINDS is a compatibility list of
built-ins, not the registry authority.

Test `test_p02_additional_adapter_through_production_mcp_and_rest` installs a
fifth no-process synthetic adapter through this same registry, discovers it
through authenticated MCP, opens it there and sends through REST. No branch
was added to the supervisor/domain for its name.

Capability restrictions intersect permissions and support. Settle is a safety
requirement, so intersection never removes it. Native dedupe/replay/managed
work and approval support remain false until their actual profiles/protocols
are implemented and verified. Declared capability alone does not authorize.

Commands: see `evidence/p02-gate.log` (13 passed including production HTTP
extension), `evidence/p02-contracts.log` (domain, imports, HTTP parity).
Native providers were not invoked in this phase.
