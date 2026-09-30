# M07 — Durable and published R4 close completion

Core 0.2.33.dev0 writes SUCCEEDED after R4 policy close confirms physical stop and releases the owned resource. The retained producer commits the terminal receipt before returning it to the consumer. Unknown outcomes remain unknown; canceling a waiter does not abandon the write or create another close effect.

The daemon execution tests now require a terminal close receipt. The Nexus integration checks SUCCEEDED through the public operation query after publication over HTTP/WSS, for manual attachment and automatic daemon startup. Native execution and Server readiness remain technical fixtures in that integration.

Real installed Pi/Codex/Claude probes are recorded separately in the Core repository. They use actual provider processes and locally constructed R4 grants; their reports include the returned stage and durable receipt stage.

## Evidence

[Coordinated results](test_runs_20260930_terminal_close.json), [artifact hashes](evidence/terminal-close-artifacts.json), and terminal-close-installed-*.json/xml/log capture the installed campaigns. Core testing is focused on kernel, journal, R4 leases, close policy and receipt contracts.

The Core wheel shared by both consumers has SHA-256 `1f119d5626e9de4c8dc2589b0941289d300e995b6a422ebc16b627be5b61fee1`.

## Remaining scope

Delayed completion after the initial observer times out, disconnected publication, nonempty reconciliation, restart/crash and disk-error recovery remain required. The other operation lifecycles and complete Server-issued native provider journeys remain in DELIVERY_PLAN.md. This increment does not close M07 or release gates.
