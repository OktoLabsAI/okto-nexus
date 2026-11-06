# PR-03 — passive project diagnostics

`okto-nexus doctor` reads the existing project and the selected local service's
ownership/readiness contract. A remote operator profile makes local service
NOT_APPLICABLE; default remote inspection reads only non-secret metadata, without
opening the OS vault or contacting the Server. Topology is resolved before either
the local lifecycle or the remote credential client. No missing home is initialized.

Explicit `--check-server` permits bounded authenticated GETs through the existing
operator transports. Remote authentication uses the human operator session and
pinned Server origin/identity. The default GET observation budget is 10 seconds,
with a maximum of 30 seconds, 64 requests and bounded response bodies. Existing
transport timeouts are reduced to the remaining budget and restored afterwards.
No login, grant issuance, configuration write, discovery refresh, executable probe,
native process, MCP negotiation, coordination message or work submission occurs.
Canonical GET presence/revision bookkeeping is not a configuration or authority
change. Local readiness has its own existing two-second maximum inspection bound.

Each proof level has PASS/FAIL/UNKNOWN/NOT_APPLICABLE, code, reason and next action.
The command reuses canonical connection observation, runtime-options and work
receipt correlation. It distinguishes current binding approval from open eligibility
and provider login. A missing version observation is NOT_PROBED/UNKNOWN. A revoked
grant reports AUTHORIZATION_REQUIRED without replacement. Pending new identity
setup remains unconfirmed; diagnosis never infers that it should create another
identity. Lost work submissions are read without resume or resubmission.

Current session control availability does not prove work completion. Only a saved,
correlated productive turn with its canonical completed result passes work_result.
The report emits IDs/state instead of prompts, outputs, credentials or arbitrary
remote error bodies. Operator authentication does not prove participant
authentication, MCP negotiation, cooperation or a test handoff; those stay UNKNOWN.
A local credential failure before transport creation cannot establish reachability.
An actual remote authentication refusal can establish that the Server responded.

## Verification and artifact provenance

- 52 source checks passed across doctor, remote operator, service inspection and
  HTTP transport. An additional pending-identity case passed separately.
- 82 installed regression tests passed on the initial candidate, including
  terminal connect/work and remote operator regressions.
- 45 focused tests passed on the final wheel after the reachability guard.
  The final suite includes all new doctor cases, remote authority/target selection
  and HTTP transport tests. The source/installed suites overlap, not additive
  distinct coverage. Neither installed run skipped a test.
- Three actual installed CLI invocations passed outside checkout: absent home
  with default and --check-server, and an offline remote metadata profile. The
  absent home stayed absent; remote files stayed byte-identical. JSON schema,
  exit codes, proof statuses and site-packages provenance were checked.
- The final clean-built wheel contains exactly 433 Python files and seven static
  assets, byte-matched to source. Unchanged Connector/Core artifacts match all
  117/130 Python payloads and existing pins. Both candidate manifests are retained.
- Ruff E9/F passes for changed production modules and new tests; whitespace and
  the fixed-scope ledger checker pass.

Initial focused checks caught an incorrect productive-action filter; it now uses
canonical turn.submit/turn.steer. A test also incorrectly expected open eligibility
from a fixture with no build observation; the expectation was corrected to UNKNOWN.
The successful 52-case source report followed those fixes. A subsequent two-case
boundary run had one failure because it waited for runtime.open to become
SUCCEEDED: this fixture leaves its receipt SUBMITTED while the session is ready
for control. The test now waits for that real contract and verifies UNKNOWN work
result with zero native turns. Its original failed XML is retained; both installed
runs include the corrected test. These fixture corrections did not weaken any
configuration, grant, checkpoint or no-dispatch comparison.

The campaign lives at `C:\Users\jpamb\AppData\Local\Temp\r3-project-doctor-2dopgiag`. `prepare.py` copies sources into an empty build
tree, builds the wheel, audits exact Python/static payloads and installs all three
packages into a fresh venv. Tests are copied outside checkout with required schema
fixtures and run using `python -I -m pytest`. The final artifact is rebuilt from
another clean source copy under `final`; its CLI campaign uses the installed
console entrypoint and imports all three packages from that venv's site-packages.

Initial installed test selection:

```text
tests/test_project_doctor_cli.py
tests/execution_r4/test_project_diagnostics.py
tests/execution_r4/test_remote_operator_terminal.py
tests/execution_r4/test_terminal_connect.py
tests/execution_r4/test_terminal_work.py
tests/test_service_inspection.py
tests/test_terminal_http.py
```

The final focused selection is the first three files plus test_terminal_http.py.
Real HTTP handlers, authorization, canonical persistence, receipts and dispatch
are exercised with synthetic native peers and an injected remote HTTP bridge/
memory vault. Actual external TLS, OS vault access, provider productivity and
native user-service registration/login/logout/reboot were not qualified.

## Fixed scope still open

DX-07 is IN_PROGRESS. This milestone implements managed-project diagnostics;
participant file/launcher validation, participant authentication, active MCP and
consented coordination/handoff smoke remain open. Connector retains its existing
host doctor; no shared cross-host output contract is claimed. DX-T12 has scoped
installed evidence for default passivity; broader diagnostic/consumer acceptance
remains recorded separately. R3 and productive M1 are incomplete. The plan hash,
59 tasks, 132 scenarios, 28 invariants and 17 acceptance criteria are unchanged.
