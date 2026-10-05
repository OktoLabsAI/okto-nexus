# NS15.03 implicit canonical endpoint selection — October 1, 2026

Existing REST and MCP opening without `endpoint_id` can now select one approved
local canonical realization matching the supplied agent, native kind and real
project root. The canonical subject must be the authenticated caller and still
needs current endpoint authority. The selected opening uses the same durable
intent, stable key and Core dispatcher as explicit opening.

Selection does not use grant filtering to hide competing configured endpoints.
Two canonical targets, or a matching canonical and legacy target, return
`AMBIGUOUS_BINDING` before any opening intent or native effect. Scans are bounded;
large stores require explicit selection. If a selected canonical binding vanishes,
the call fails rather than falling back to legacy execution. Existing legacy-only
selection keeps its prior authorization path. Remote realizations continue to
use explicit path-free connect or the R4 API.

Directed tests exercise both transports and explicit/implicit selection, stable
retries, canonical receipts and close, missing grants, disabled endpoints,
protocol readiness and competing canonical/legacy targets. The installed campaign
also covers canonical connections/keys and existing legacy endpoint, self-connect
and grant callers. No schema, Core artifact or Connector change is included.
Provider peers and readiness qualification remain fixture-local.

NS15.03 remains partial. Boot currently runs before embedded inventory and dispatch
startup; it must be moved to the ready canonical composition and retain its stored
operator/owner authorization. Delivery and event projection also remain before
native loader/codec removal. Normative TR4-15-03, M12 and release gates remain open.
