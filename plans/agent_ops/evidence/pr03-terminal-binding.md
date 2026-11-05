# PR-03 — terminal decision for Connector binding proposals

Human operator CLI reviews and decides the original immutable Connector binding proposal through the existing approval API. Review includes actor, Server, subject, workspace, executor, installation, effects, revision and expiry. Participant authority cannot substitute for the operator; expiry, policy drift, rejection and conflicting decisions remain fenced. Lost decision responses recover the canonical receipt without another POST. The real Connector onboarding service and background continuation reopen persisted state and apply the original request once with the participant credential, producing one binding and grant. 30 source Server tests, 17 source Connector tests and 153 coordinated installed tests passed; 24 focused installed cases passed after the Connector README metadata rebuild, with unchanged Python payloads. Synthetic inventory and HTTP adapters establish the contract; real two-host provider work, OS vault/TLS and full M1 remain open.

`okto-nexus operator approval APPROVAL_ID --profile NAME` only inspects. An explicit
`--decision approve|reject` presents the canonical scope and asks for confirmation;
scripts must supply its exact `--confirm REVIEW_REVISION`. The normal human operator
profile verifies the pinned origin, Server and active session before any decision.
No operator key or cookie enters Connector state or participant requests.

The existing ApprovalService detail hook now exposes the immutable public binding
proposal and its current status/expiry. The transactional decision handler, proof,
actor, policy guard and participant apply remain the same. No new approval queue,
grant issuer, migration, transport revision or native harness action is introduced.
Approval alone commits proof; the original Connector applies its existing intent.

Read-after-loss recovery uses the same approval ID, original revision and canonical
receipt. It refuses a different decision, decider, justification or archived item.
Pending decisions are re-read before POST, and the Server remains authoritative
for the final race, expiry and current policy. The Connector reports approval IDs
and a command to run on the operator client, retaining its durable request ID.

## Validation

- Source Server/CLI plus existing binding approvals: **30 passed** in
  `pr03-terminal-binding-source.xml` (100.82 seconds).
- Source Connector wizard/background suite: **17 passed** (1.99 seconds).
- Coordinated installed campaign: **153 passed, zero failures/errors/skips** in
  `pr03-terminal-binding-installed.xml`. It covers new terminal decisions, existing
  binding/replacement/machine-policy gates, human operator transport/authentication,
  HITL and archive regression, and copied Connector configure/background/setup tests.
- Final artifact: **24 focused installed tests passed** in
  `pr03-terminal-binding-final.xml`. Connector was rebuilt after its README update;
  archive comparison proves only METADATA and RECORD changed. All Python payloads
  are identical to the broad campaign. Reports overlap and are not summed as
  distinct coverage. Initial and final wheel hashes are retained separately.
- Production and new test modules pass Ruff E9/F; whitespace and fixed-plan ledger
  coverage are checked before commit.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-terminal-binding-esj0yv00`.
Fresh environment imports are verified under `python -I`; tests and fixtures are
copied outside the source checkouts. All **429/114/130** Python payloads in Nexus,
Connector and Core match their source bytes. Exact hashes are in
`pr03-terminal-binding-wheels.json`; the Nexus CI Connector wheel/manifest are
updated together. Package versions remain 0.3.3 / 0.0.12 / 0.0.14 on their feature
branches. Core source and its pin are unchanged.

The integrated case uses real Server HTTP handlers, SQLite approvals and proof
transactions, Connector BindingOnboarding/StateStore and background continuation.
Only HTTP wiring, inventory/native installation and protected-vault backend are
synthetic. Participant requests are checked to contain only the participant key,
and persisted Connector state is checked to exclude the human session. Reopening
the store models process restart; no actual daemon restart or two-host deployment
is claimed by this case. The final state has exactly one proposal, approval,
binding and scoped grant; another background pass sends no request.

## Remaining acceptance

DX-T32's pending proposal/decider separation contract is verified. DX-T40/45/46
remain partial until the complete real-provider local and Connector campaigns
are qualified. New remote identity and unified default onboarding, login-start
review, participant initialization, preset evolution, dashboard introduction,
remaining SVC qualification and all later ATN/OBS fronts remain open. No personal
service, native task, real credential, provider inference, release or merge was
performed. The outstanding isolated native-service approval request is unchanged.
