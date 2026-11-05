# PR-03 — initial Nexus terminal connection facade

Windows 11 `10.0.26300`, Python 3.13.1; Nexus `0.3.3` on
`feature/v0.3.3`. Connector `0.0.12` and Core `0.0.14` are unchanged in this
increment. The full R3 objective, PR-03 and M1 remain incomplete.

`okto-nexus connect` now resolves the selected local service through the same
saved-context resolver as `service`, starts/reuses it on ordinary invocation,
and conducts the existing operator HTTP setup from the terminal. `--plan` uses
passive inspection and refuses to bootstrap a stopped service. An atomic,
exclusively locked local profile retains the review, setup ID, request revisions,
submission checkpoints and canonical binding references without credentials or
conversation history. No CLI path writes the Server database directly.

The small `project-generalist` revision 1 preset resolves to ordinary connection
configuration: native harness/model/project settings inherited, tool access
`ask`, per-sender sessions, automatic eligible message delivery, and requested
60-minute / 20-action execution limits. It does not change existing agent roles,
permissions or broadcast-handoff opt-in. Its origin is stored in the existing
Finish receipt and exposed in setup reads, with no migration or template store.

Review explains the actual installation check and model-response connection test.
An exact review hash or interactive confirmation precedes these effects. Request
content is checked against the retained review on resume. A lost version-check
reply leads to inspection of the same candidate, not another command. Test and
Finish use the canonical recovery route/checkpoints; a missing test remains
unconfirmed. Reconnect reads current configuration and does not reissue grants
or apply defaults. A unique authorized binding for an explicitly selected agent
and project can be adopted; explicit conflicting host/workspace/provider choices
are refused. Paths alone never select or create an agent identity.

## Validation

- Source terminal/transport cases: **18 passed**.
- Source service context/start/upgrade regression: **58 passed**.
- Source actual CLI/service plus canonical setup/recovery regression: **34 passed**.
- Additional canonical binding reuse case: **1 passed** before the final explicit-choice checks.
- Final installed suite: **112 passed, zero skips/failures/errors**.

The final installed suite includes the final explicit-choice checks and both old
CLI compatibility cases. All three package origins are asserted inside a fresh
venv outside the checkouts, with `python -I -m pytest` and copied tests. The 419
Nexus, 114 Connector and 130 Core Python wheel payloads match source byte-for-byte.
The wheel hashes are in `pr03-terminal-connect-wheels.json`; the environment is
`C:\Users\jpamb\AppData\Local\Temp\r3-terminal-connect-npiyfqw9\validation`.

The disposable real-process case first calls `connect --plan` on an absent home
and confirms no bootstrap/state directory. Ordinary connect then starts the
Server, reaches its real loopback operator API and reports the intentionally
missing agent. A second connect reuses the same PID/generation after the first
CLI exits. Explicit `service stop` finishes with `DRAINED`. Harness integrations
are disabled in that process campaign; it does not test productive work.

Application/HTTP integration uses real authorization, discovery publication,
version-observation storage, setup validation and Finish transactions. Native
build qualification, version-command execution and model response are simulated
in that fixture. It covers exact review consent, loss after installation check,
Test and Finish, lost test cache, canonical project reuse, unknown preset
revisions, and preserving a later tool-policy edit and its grant state.
Transport tests cover interrupted bodies, oversized/malformed responses,
canonical receipt absence and refusal to treat remote addresses as loopback.

Initial fixture runs lacked architecture observations on the synthetic binary.
Adding architecture to the probe result was correctly refused as an installation
identity change. The final fixture supplies architecture in discovery, retaining
it through the mocked version command; no production qualification gate was
weakened. Final installed results supersede those failed development runs.

JUnit: `pr03-terminal-connect-nexus.xml`, `pr03-terminal-connect-service.xml`,
`pr03-terminal-connect-regression.xml`, `pr03-terminal-connect-reuse.xml`,
`pr03-terminal-connect-installed.xml`. Ruff and whitespace checks cover the
changed files. User instructions and limitations are in `docs/terminal-connect.md`.

## Scope still required

This implementation currently selects an existing authorized agent. Unified
agent creation/name/role/coordination permissions, login-start selection in the
review, participant `init`, remote topology integration, operator-session CLI
authentication, complete terminal work/questions/decisions/results, preset
evolution and dashboard introduction remain open. The minimal runtime defaults
do not by themselves satisfy the complete DX-18 project preset. No real provider
login, inference, productive task, native task registration or release is claimed.
The original prepared native campaign still awaits its separately requested
authorization. None of these remaining requirements has been removed from R3.
