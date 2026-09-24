# P12 — positive mirror observation (in progress)

Parent `a6a18b4dfeaa0f8272ebf3ecb6b410c8af5a0946`. Existing negative qualification for the four built-in adapters remains valid: none demonstrates context_without_execution. They must not receive a second send_turn as a substitute for observation.

New behavioral reproducer: tests/test_runtime_mirror_observation.py registers a processless context-only adapter through the existing trusted AdapterRegistry, creates its approved profile/endpoint via actual operator REST, opens it with mirror_only/response_policy=none and opens an exclusive Pi fixture executor for the same canonical worker. Authenticated MCP creates one message. The executor receives its one turn, but the context observer receives nothing. Windows handle46168 exited1: **1 FAIL33.96s**, at the explicit observation wait, with no import or setup error. Exact command and changed-file hash: [RED manifest](evidence/p12-mirror-observation-red-windows.json).

The test's observe_context(session,envelope) is a proposed optional version1 adapter capability, not a completed production contract. It stores context without calling send(), requests no response and must leave the original inbox consumer reservation intact. No native protocol is asserted to implement it. T-CONS-07 remains NOT_RUN/partial until integrated positive, negative, recovery, authorization and bounded-worker coverage is green.

Next implementation must persist observation transport attempts as subordinate state of the original logical delivery, revalidate actor/recipient/endpoint/profile and effective capability, use bounded owner workers outside SQLite writer transactions, and preserve uncertainty without blind replay. An observer cannot ACK the executor reservation, reserve executable budget, claim work, publish a result or complete a handoff merely by receiving context. Public diagnostics must distinguish observation from execution. Reuse the current owner/wake/lifecycle mechanisms; do not introduce another logical work queue.

No production code changed in this reproduction. Do not count this RED as PASS or use it to qualify the four native connectors.
