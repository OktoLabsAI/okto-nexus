# Operator initiation with separate subject execution authority

The R4 intent API previously accepted only the authenticated agent's bindings.
An operator could prepare another agent's installation and binding, but could
not initiate its canonical runtime operations. The installed previous wheel
reproduced the missing contract field as HTTP 400 in
`evidence/operator-runtime-before.xml`.

`POST /v1/runtime/intents:resolve` now accepts optional `agent_id`. Omission keeps
the existing self-agent behavior. A different subject requires the authenticated
operator; payload flags cannot create operator authority. The operation records
the operator as actor and the selected agent as subject. Scope revisions, session,
workspace, lease, grant and execution budget remain the subject's. Administrative
operator privilege does not manufacture or replace that execution grant.

Migration 099 adds a nullable actor guard to durable client intents. Old self-agent
intents need no new proof. Newly represented requests record the current operator
identity/policy digest. Admission and pre-send dispatch revalidate it; lease and
capability authority also validate the initiating operator for represented
openings. Missing proof never upgrades a historical record into operator authority.
Initial prompt children retain both identities and the guard. Native decision
authorization retains its existing independent proof path.

Operators can explicitly reuse a compatible subject opening, read the same intent
after a lost reply, and submit/steer/interrupt/close through canonical admission.
Replays retain the operation ID and do not create another process. Historical
reads remain distinct from current execution eligibility. Runtime-options now
projects the subject's grant for operator callers; technical readiness remains
an independent gate. No wire schema or Core/Connector package change was needed.

## Installed verification

- Windows Python 3.13.1: **143 passed**, 1340.63 s, in
  `evidence/operator-runtime-installed-windows/`.
- WSL Linux Python 3.12.13: **143 passed**, 828.16 s, in
  `evidence/operator-runtime-installed-linux/`.
- Both runners verified all three installed packages against the pinned wheels
  and ended with PASS, exit 0, and `changed_inputs: []`.
- Coverage includes the complete five-action operator cycle and exact budget
  consumption; actor/subject namespaces; recovery and reuse of a subject's opening;
  initial prompt provenance; nonoperator refusal; operator change between resolve,
  admission and send; subject grant revocation; lease/capability invalidation;
  runtime-options, embedded dispatch, session reuse, initial turns, NS06, session
  capabilities, native decisions, migrations and the NS15.05 documentation audit.

An additional installed test exercises operator HTTP admission, remote WSS lane
negotiation and actual Server lease issuance, preserving the subject and grant
and recovering the same operation. It passed on Windows (15.45 s) and Linux
(9.29 s). No native provider is launched in that specific case. Evidence:
`operator-remote-windows.xml` and `operator-remote-linux-reviewed.xml`.
The exact tested helper is now `tests/execution_r4/test_operator_remote.py`,
SHA-256 `9815c122fe6017011e8c192e365382646a6a14596cf405d8a00fb8455125c3b3`.
It ran from an external temporary directory while the main campaign's inputs
remained frozen; it was copied unchanged into the repo only after both ended.

Initial source campaigns are retained, including the 22-pass/two-failure report:
one assertion still expected the old operator restriction, and another confused
an unprobed synthetic installation with technical readiness. Both expectations
were corrected before the installed campaigns; no product behavior was weakened.
The first remote invocation selected an overly broad pytest root and failed
collection; the isolated attempt then used a relative WebSocket URL and was
refused. The reviewed fixture uses the same explicit WSS origin as the existing
remote tests. Those failures remain in `operator-remote-linux.xml` and
`operator-remote-linux-isolated.xml`. The shared Starlette/httpx deprecation
warning remains unchanged.

## Artifacts and reproduction

Nexus wheel SHA-256:
`b09dbba597ab8d109298afedd60b32a4f995b203d7a98bfd8443cf6b08756b4b`.
Nexus sdist SHA-256:
`f05687eb318b5a76c65aa8ca5dfdd2a6bd3353e13b310c57454a0d592780d18c`.
Core .56 wheel remains
`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`;
Connector remains
`93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

Build using `python tools/build_validation_artifacts.py --output <dist>` and
install that wheel plus the manifest's Core/Connector wheels in an isolated test
environment. With that environment's Python, invoke `tools/ci_installed.py test
--wheel <wheel> --output <fresh-evidence-dir> --tests
tests/execution_r4/test_operator_runtime.py tests/execution_r4/test_operator_remote.py`.
The campaign JSON lists the additional regression files and frozen input hashes.
The supplemental remote runs used `python -I -m pytest`, an explicit temporary
root, disabled cache provider and only `tests/execution_r4` as the helper path.

These are same-machine, installed application tests with synthetic native peers
and qualification fixtures. They do not prove provider/platform qualification,
independent-host acceptance or completion of the runtime operation UI. The next
UI increment can now use the operator's real credential without impersonating
the subject. M13 and G0–G3 remain open; CI remains deferred by user instruction.
