# Canonical native decisions in the dashboard — 2026-10-02

Approvals now recognizes `execution.native.respond` and opens a dedicated
review panel. Permission, question and typed MCP form responses use the R4
approval-decisions endpoint with the reviewed key, revision, hash and CAS token.
Generic approval buttons no longer handle these requests. Denial is explicit;
form defaults are not automatically accepted. Existing backend authority and
expiry checks remain unchanged.

The browser saves immutable decision metadata before submission, scoped to
Server, actor and request. Answers remain in memory and are absent from browser
storage. Reload reads the original decision without resubmitting; an uncertain
input retry requires explicit re-entry of the same answer. A click lock prevents
concurrent duplicate submissions. Storage failure prevents POST. The display
separates canonical confirmation from native delivery and never treats a recorded
decision as proof that the provider applied it.

## Validation

TypeScript checking and the isolated frontend/package build passed. Development
wheel SHA-256: `38e0b232fba2703d4c5bba4ebb345919a31ce2f4d061c7a158e89b46d11c1777`.
Sdist: `51747ae6d10cca430509a22a45ceb036736b0155d283a5cdc204a4f763265c41`.
Core .56 and Connector dependency wheels remain respectively
`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`
and `93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.
The user's preexisting static assets were preserved; the wheel contains freshly
compiled assets from an isolated copy.

- `evidence/native-decisions-ui-reviewed.xml`: 29 source passes (453.46 s),
  comprising six browser cases and 23 backend authority/CAS/replay/input cases.
- `evidence/native-decisions-ui-installed/`: 11 passes and two fixture setup
  errors (186.73 s); campaign status remains FAIL, with `changed_inputs=[]`.
  The synthetic MCP form omitted the required `turnId`; Core correctly refused
  ingress. Production validation was not relaxed.
- `evidence/native-decisions-ui-installed-reviewed/`: the two corrected form
  cases passed (33.56 s), status PASS and `changed_inputs=[]`, using the same
  product wheel. These results supplement the prior eleven passes; they are
  not a single thirteen-pass campaign.
- `evidence/native-decisions-ui-source.xml` retains the initial selector setup
  failure: an exact Approvals label did not match its pending-count badge.

Installed tests used Windows/Python 3.13.1 and headless Edge, real installed HTTP
handlers through TestClient, grants, SQLite and canonical outbox operations.
They cover permission/question/form confirmation, lost replies and reload,
double click, denial, expiry while open, storage failure and revoked authority.
The selection also verifies an existing runtime operation cycle, CAS race and
NS15.05. Synthetic answers are checked absent from browser storage and database
snapshots. Screenshots are retained in `evidence/native-decisions-ui-screenshots/`.

To reproduce, install the wheel and pinned dependencies in an isolated environment,
set `OKTO_NEXUS_UI_CAMPAIGN=1` and `OKTO_NEXUS_UI_INSTALLED=1`, and invoke
`tools/ci_installed.py test --wheel <wheel> --output <new-directory> --tests
tests/execution_r4/test_native_decision_dashboard.py` with that interpreter.

## Scope still open

Native requests and host qualification are synthetic in this UI campaign. Actual
provider application, remote dispatch acceptance, Linux browser acceptance,
complete history and uncertain-session recovery remain open. This increment
does not qualify macOS containment, independent hosts or a final release tuple.
Independent-host acceptance remains manual with the user; hosted CI is deferred.
No M10/M13 milestone or G0–G3 product gate is closed by this evidence.
