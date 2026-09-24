# P05/P06 — approved equivalent-endpoint fallback

Parent23f83ccd89ccf010ffb48c14a5d2b77d3d7ed346, feature/v0.2.0.
Schema061, surface56, identity reference24. Final plan gate NOT PASSED.

## Reproduction and implementation

An actual REST/MCP message for a canonical agent selected endpoint A. Its adapter
refused the new turn before native write because an internal turn occupied that
lane. B was enabled/approved in the same explicit interchangeable group, but the
dispatcher kept A as its sole retry target. The expected safe
send to B failed: **1 FAIL8.83s**, remaining RETRY_WAIT instead of SENT_UNCONFIRMED.
The RED used only existing APIs and states, not a missing proposed field/import.

RuntimeDeliveryPlanner.candidates now shares normal and fallback filtering. Its
fallback method requires a new conversation, current source authority, a nonempty
operator-approved selection_group, same agent/workspace, approved target profile,
compatible effective capabilities and no prior attempt at the alternative.
Ready targets win, then priority, then stable ID inside that approved group.
Feature-disabled attach endpoints are excluded. No registry enum is duplicated.

The serve composition installs the selection callback on RuntimeDispatcher.
Only a typed RuntimeCommandNotSent enters this path; generic startup/I/O exceptions
remain ambiguous without explicit proof. Controls, captured-result relays,
conversation continuations and managed work never borrow another binding/grant.
RuntimeLaneBusyBeforeWrite can still retry its original endpoint when no valid
alternative exists. The existing three-attempt retry policy remains bounded.

Migration061 adds admission_binding/next_binding JSON to the existing outbox and
their immutable history snapshots, including endpoint/profile revisions. A computed
dispatch-lane index supports target selection/order. No second delivery/work queue
is added. A's proof and B's pinned target commit together as RETRY_WAIT; the next
fenced claim assigns a new attempt to B. Both original and target approvals and
current actor authority are revalidated before effects. Revision changes deny
dispatch; even original-profile revocation cannot be bypassed by choosing B.

The canonical message/envelope/hash/causal admission/inbox reservation never change.
EnvelopeConnector frames the current server-owned transport_binding separately
from the immutable admission snapshot. The target's approved profile is explicit,
but neither binding nor prompt grants task authority. On-demand open keys include
the fallback endpoint, so A's previous open does not stand in for B's lifecycle.
All startup, secrets and native writes remain outside SQLite write transactions.

The four built-in envelope adapters advertise trusted transport_binding_contract1.
An external adapter must explicitly declare and implement that versioned payload;
endpoint/profile metadata cannot claim support. The fifth processless registered
adapter is exercised through serve/MCP, with both opt-in and legacy exclusion.
This is a Nexus envelope contract, not an invented native ACK or deduplication.

## Evidence and exact commands

All commands use rtk proxy; Windows .venv/Scripts/python.exe; Linux WSL Ubuntu
cwd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus, interpreter
/var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python.

- RED: `-m pytest -q --tb=short tests/test_runtime_endpoint_fallback.py`:1 FAIL8.83s.
- Initial fallback plus safe retry: `-m pytest -q --tb=short tests/test_runtime_endpoint_fallback.py tests/test_runtime_safe_retry.py`:
  **12 PASS32.62s**.
- Expanded fallback: same first file, **13 PASS36.68s**, then **15 PASS42.67s**.
  Counts overlap and are not summed.
- Broad selection: `-m pytest -q --tb=short tests/test_runtime_endpoint_fallback.py tests/test_runtime_safe_retry.py tests/test_runtime_not_sent_recovery.py tests/test_runtime_attempt_history.py tests/test_runtime_outbox.py tests/test_runtime_scheduler_fairness.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_commands.py tests/test_migrations.py`:
  **Windows110 PASS340.13s; Linux110 PASS387.26s**, one Starlette warning each.
  This ran during development; the final JSON/index and extension-contract guard
  were added afterward/during the campaigns and are covered by later selections.
- Capability/administration compatibility:
  `-m pytest -q --tb=short tests/test_runtime_effective_capabilities.py tests/test_runtime_effective_requirements.py tests/test_runtime_endpoints.py tests/test_runtime_backup_restore.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **Windows61 PASS153.47s**, one Starlette warning.
- Final JSON/index/history selection:
  `-m pytest -q --tb=short tests/test_runtime_endpoint_fallback.py tests/test_runtime_attempt_history.py tests/test_migrations.py tests/test_frente1_resources.py tests/test_import_boundary.py`:
  **Windows41 PASS75.65s; Linux41 PASS89.37s**. Collected before final extension opt-in cases.
- Initial extension guard:
  `-m pytest -q --tb=short tests/test_runtime_endpoint_fallback.py tests/test_pr34_remediation.py -k "fallback or additional_adapter"`:
  **Windows20 PASS34 deselected77.75s**. Final opt-in/legacy variants, same command: **Windows21 PASS34 deselected76.01s; Linux21 PASS34 deselected79.96s**. All test sessions terminal.
- Metadata: seven surface-test files from the prior unit, exact suffix
  `-k "surface_revision or nexus_info_features"`: **9 PASS245 deselected5.65s**, one warning.
- Ruff changed Python files and git diff --check PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 23f83cc`:
  unchanged OFF43 tools40448 characters10112 estimated tokens; ON51 tools47730
  characters11932 estimated tokens. Surface55 to56; fetched identity23 to24.

Coverage includes ready/on-demand B, separate approved profiles, unchanged envelope
bytes/hash, one logical delivery, one write in B, original-versus-current binding
framing, REST/MCP inspection parity, immutable selection audit, group/scope/agent/
profile isolation, five revocation cuts, uncertain post-write exception, continuation
affinity and endpoint-scoped handoff grants. A real owned Codex Python protocol
peer with an unqualified version starts a thread but writes no turn/start; the same
operation subsequently reaches an approved Pi-shaped fixture endpoint. No model
or provider is involved in that protocol test, and no native Pi execution is claimed.

No native provider/model campaign for this unit. Latest real Codex/Claude evidence
remains d76b78c; Pi/dedicated attach native NOT_RUN. Protected local assets untouched.
Next: audit the complete acceptance matrix against current code/evidence, close
remaining scheduler/crash/performance/operational gaps, run immutable full/native
qualification, and build/reinstall0.2.0. No phase or final-gate promotion here.
