# PR-04 — existing participant init and durable local stages

Validation: 2026-11-05; delivery finalized 2026-11-06 (America/Sao_Paulo).
Windows 11 10.0.26300, Python 3.13.1.
Nexus 0.3.3, Connector 0.0.12 and Core 0.0.14 remain development candidates on
their authorized feature branches. The fixed R3 plan and full M1/M2 scope have
not changed. This is an incremental implementation of DX-03/04/05/06.

## Behavior and boundaries

`okto-nexus init --mode participant` and `connect --mode participant` share the
same host implementation. It selects an explicit origin, existing identity and
workspace, imports an existing key using hidden input/stdin/an explicitly named
environment variable, and authenticates a preparation GET using Bearer. Remote
HTTP and redirects are refused; explicit loopback HTTP is plaintext.

The new `/v1/connections/participant` route checks current identity, workspace
and MCP method policy without creating identities, workspaces, sessions, grants
or bindings. Runtime policy remains unchanged. The canonical auth middleware
can update last-seen timestamps; this is not described as zero database writes.
Approval also binds the actual identity/policy digest, avoiding aliasing of
read-only execution revision projections across several unpersisted changes.

The local review stores no credential or original file bytes. Its hash includes
the selected file identity/source/postimage/access revision, client contract,
Server context and setup ID. Approval precedes a dedicated vault write and
selected-entry apply. OS-vault failure has no plaintext fallback. Existing
third-party configuration is preserved and never executed. Generic output is
manual guidance; the complete host receipt is explicitly not a portable export.

Core's optional `prepare_file(path, kind)` hook lets the trusted host protect
empty backup/replacement files before sensitive bytes are written. Tests found
that Windows `SetNamedSecurityInfo` can merge inherited ACEs into the copied
DACL. The host now preserves the exact descriptor using `SetFileSecurity` and
checks its access revision before writing the replacement. Backups/new files
are private; original access policy remains unchanged. The adjacent lock and
CAS still cannot eliminate races from noncooperating external writers.

Separate durable `credential_pending`, `credential_stored`, `file_pending` and
`done` stages preserve the setup ID. Lost checkpoint responses recover through
the same vault namespace and exact file postimage. An uncertain file changed
afterward is preserved and refused. Confirmed completed receipts allow unrelated
later edits but refuse modification of their owned entry. Local failure never
compensates by deleting a Server identity. Already approved intent can resume
without another approval; refresh is limited to an unapproved review.

Output distinguishes configuration applied from readiness. Identity/entry can
pass while actual client credential context, reload and MCP remain unknown.
No task is submitted. The user-facing behavior and limitations are documented
in [terminal participant](../../../docs/terminal-participant.md).

## Validation

- `pr04-participant-init-core-source.xml`: **105 passed** (contract, managed
  boundary, JSON/TOML editors, persistence callback and public docs).
- `pr04-participant-init-nexus-source.xml`: **22 passed** (20 participant cases
  and two HTTP-only CLI regressions). The final installed run additionally
  includes the last uncertain-file/later-edit recovery case and retained
  approval behavior.
- `pr04-participant-init-core-installed.xml`: **104 passed, one failure** in
  the documentation link fixture. The disposable copy lacked linked plan/docs
  files, while the original source documentation passed. After copying the plan,
  `core-followup.xml` still found a missing `CONTRIBUTING.md`; copied every
  referenced local fixture and `core-docs-final.xml` passed the affected case.
  All reports are retained: **105 unique cases passed**, no runtime/wheel change
  was needed for these fixture corrections.
- `pr04-participant-init-connector-installed.xml`: **80 passed**, direct MCP
  configuration and approved MCP/native managed launch regressions.
- `pr04-participant-init-nexus-installed.xml`: **36 passed**, including **21
  participant**, two CLI and 13 managed terminal-connect cases.
- The redirect test runs a real temporary HTTP server and confirms one initial
  Bearer request and no redirected request. Other participant HTTP tests use
  real FastAPI/auth/SQLite through an in-process wire adapter.
- Credential storage tests use a synthetic vault backend, including failure
  and lost-checkpoint recovery. Windows ACL checks use real temporary files.
  They do not prove actual client credential inheritance or actual OS-vault
  credential storage. No real user key, personal config or model was used.
- `pr04-participant-init-import.json`: installed Core import/render produced no
  network/process/thread effect or non-code file read. Static import boundary
  auditing covered all 131 Core Python files.
- Ruff E9/F and `uv lock --check --find-links vendor/wheels` passed.

Campaign: `C:\Users\jpamb\AppData\Local\Temp\r3-participant-init-6elabogi`.
Core and Nexus were built from fresh source copies. The three wheels were
installed in a fresh venv; copied tests ran with `python -I -m pytest` outside
the checkouts. SQL fixture resources came from the Nexus wheel. Raw Python
payload sets/bytes match: Nexus **441**, Connector **117**, Core **131**. Nexus's
seven static assets match too. Hashes are in `pr04-participant-init-wheels.json`.
Core SHA-256 is `5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb`;
the same artifact is vendored in both consumers. No package release was uploaded.
Core commit/push: `5d31784`; Connector candidate commit/push: `7bdd0f5`.

## Remaining scope

DX-03/04/05/06 and PR-04 remain in progress. Actual launcher/GUI environment
delivery, OS-vault integration qualification, participant doctor, authenticated
MCP negotiation, session/cooperation smoke and work are still pending. Approved
policy drift requires inspection; automated compensation/removal and cleanup
are not delivered by this increment. Other OSes and external client versions
are unqualified here. Prior real binary format-reading evidence still proves
parsing only. Productive M1 and the full fixed goal remain incomplete.
