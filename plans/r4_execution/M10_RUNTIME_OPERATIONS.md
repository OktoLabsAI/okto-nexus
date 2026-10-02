# Runtime operations in the installed dashboard — 2026-10-02

Agents → Connections now exposes reviewed canonical runtime actions for the
selected agent, executor, installation and binding: start/reuse, submit a turn,
steer, interrupt and close. Operator provenance and the subject's grant remain
enforced by the existing backend; the UI does not create execution grants.

Start distinguishes automatic unambiguous reuse, explicitly new sessions and
specific existing sessions. Steer/interrupt distinguish native turn IDs from the
current run at execution time. An optional initial message retains its separate
follow-up operation. The panel reads admission and executor state, session/lease
state and available captured output; an unknown result is not treated as success.

Before the first mutation, the tab saves the immutable request and message under
Server ID, authenticated actor, subject and binding. Storage failure prevents
resolution. Resolution has no native effect; submission is a separate explicit
step. Reload and polling only read the original intent and operation. Uncertain
submission retains the same identity/body and cannot become a replacement
action. A local click lock prevents duplicate concurrent submissions. Reading
the original opening receipt for a reuse resolution does not replace explicit
admission of the newly reviewed reuse request. Late callbacks are scoped to the
mounted request; polling cannot erase the durable submission-attempt flag.

## Validation and artifacts

Development wheel SHA-256:
`4705d1de073b8bd81be49d6045dbea7d4cca001c89776660a7a5a8069a22db2f`.
Sdist SHA-256:
`15638321dceb5bf34b9e6619ac9a1ecf42b64bcfb252492b352185b525755169`.
Both were built by `tools/build_validation_artifacts.py` from an isolated copy
with freshly compiled dashboard assets. The user's preexisting static files
were preserved. These are development validation artifacts, not the final M13
freeze. Core remains .56 (`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`)
and Connector remains the issue-2 wheel
(`93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`).

`evidence/runtime-operations-ui-installed/` records installed package-byte
verification and **25 passes in 212.86 s**, on Windows/Python 3.13.1 and headless
Edge, with `changed_inputs=[]`. This includes six new browser cases, existing
selection/preparation journeys, ten operator authority cases and NS15.05.
The browser sends requests to the real installed HTTP app through TestClient;
SQLite, grants, admission, dispatcher and Core seam are exercised. Build
qualification and the native provider are explicitly synthetic fixture boundaries.
No actual provider or independent remote host is qualified by these results.

The new browser cases cover full five-action cycles, explicit reuse without an
extra open, dropped resolution/admission replies followed by reload, authority
revocation after review, storage refusal before POST, initial-message follow-up
and double click. Each cycle leaves exactly five canonical operations, one
native open and one dispatch attempt per operation. Reuse recovers the original
opening operation. Status screenshots were visually inspected and are retained
in `evidence/runtime-operations-ui-screenshots/`.

Retained source-run history:

- `runtime-operations-ui-source.xml`, `runtime-operations-ui-reviewed.xml`,
  `runtime-operations-ui-native-fixture.xml`, `runtime-operations-ui-browser.xml`:
  fixture setup failures while making the synthetic candidate explicitly
  observed/qualified; production readiness checks were not relaxed.
- `runtime-operations-ui-qualified-fixture.xml`: HTTP browser execution exposed
  unavailable `crypto.randomUUID`. Request IDs now use `getRandomValues`, as the
  existing consent flows do, including HTTP LAN deployments.
- `runtime-operations-ui-http.xml`: four browser cases passed (84.06 s).
- `runtime-operations-ui-recovery.xml`: two additional cases passed (30.50 s).

To reproduce with this wheel installed and the pinned dependencies available:
set `OKTO_NEXUS_UI_CAMPAIGN=1` and `OKTO_NEXUS_UI_INSTALLED=1`, then run the
installed interpreter with `tools/ci_installed.py test --wheel <wheel> --output
<new-directory> --tests tests/execution_r4/test_runtime_operations_dashboard.py
tests/execution_r4/test_embedded_preparation_dashboard.py
tests/execution_r4/test_runtime_selection_dashboard.py
tests/execution_r4/test_operator_runtime.py
tests/execution_r4/test_ns15.py::test_ns15_05`. The runner checks imports and
installed bytes outside the checkout, then verifies unchanged campaign inputs.

## Remaining acceptance

This removes the missing basic runtime controls from M10; it does not close M10,
M13 or a product gate. Native approval/input decisions, complete history and
uncertain-session recovery journeys, broader accessibility/language acceptance,
remote daemon UI integration, actual providers and the required OS/Python/fault
matrix still need their respective evidence. Independent-machine acceptance
remains manual with the user; hosted CI remains deferred. Native macOS still
requires the launchd coalition backend and native qualification.
