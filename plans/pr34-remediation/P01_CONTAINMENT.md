# P01 containment — implementation, not final release

Base milestone: 63c9623. Changes are on feature/v0.2.0 only.

Shared application policy `runtime_authorization.authorize_runtime` now gates
MCP and REST reads and controls before connector construction. An absent
principal is denied; same-machine REST has a dedicated trusted ContextVar
set by the authenticated boundary, not inferred by the tool from None.
An explicitly supplied REST key is authenticated even on loopback.

Open requires an existing active Agent. Supervisor no longer writes Agent
rows. Legacy role must match; metadata is validated session data. A temporary
per-agent starting/live fence prevents two executors until P05 provides
durable binding/consumption selection. This temporary restriction does NOT
satisfy multiendpoint acceptance.

Flags use the existing config/settings path:

- `OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS=false` by default; publication
  requires restart and existing handlers recheck admission on every call.
- `OKTO_NEXUS_FEATURE_HARNESS_ATTACH=false` is a separate additional opt-in.
- OFF does not construct the MCP supervisor or launch serve's watchdog.

Environment and extra-argument diagnostics are redacted. This is not yet
the approved-profile/secret-resolution system required by P03/P04.

Validation:

```
.venv/Scripts/python.exe -m pytest tests/test_pr34_remediation.py -q -k "p01 or profile_is or unknown_agent or authenticated_mcp or unconfigured_surface or backend_diagnostics or keyed_loopback or fabricate"
```

Observed 28 PASS, 7 deselected; `evidence/p01-gate.log`. Tests exercise real
HTTP/MCP authentication, REST parity, all four synthetic peers with explicit
opt-in, cached-tool denial, metadata compatibility and duplicate-start fence.
The seven later-phase reproductions are still open, not marked passed.

Legacy validation command and output: `evidence/p01-legacy.log` (config,
authentication, feature flags, HTTP parity, import boundary and surface metrics).
Surface revision 35 records opt-in and identity semantics. Growth discounts
for harness schemas are now conditional on their actual publication.

Outstanding: persisted delegation, approved profiles, runtime ownership,
outbox/consumer arbitration, journal, canonical work flow, durable causality,
multiendpoint selection, Windows protocol/process failures and real connector
campaign. No claim of secure final enabled functionality or readiness to merge.
