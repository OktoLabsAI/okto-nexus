# Preserve the initiating embedded failure — October 2, 2026

The Linux/Python 3.11 full CI job reported a missing-provider-credential test
whose diagnostic had become `RuntimeError: The embedded Core host is shutting down`.
Inspection found three concurrent producer paths unconditionally replacing the
same `EmbeddedDispatchOwner.failure` field: execution, renewal and maintenance.

Those paths now record an error only when no earlier error exists. Every failing
path still invokes containment; no work is retried, no receipt is synthesized,
and storage/containment recovery fields and shutdown ownership are unchanged.
The assignment precedes any await on the owning event loop.

## Evidence and scope

Three deterministic unit cases reproduced the replacement before the fix, covering
each secondary producer. They exercise the actual producer catch paths with
injected errors and an observed containment callback. They verify error arbitration,
not real provider timing or OS containment. The original public provider-vault
integration tests remain unchanged. Combined source checks passed 12 tests.

Earlier attempts to force the race through live receipt/maintenance callbacks
instead stalled their fixture before reaching the intended ordering. Those failed
experiments were removed from test source and their JUnit reports are retained in
[discarded fixture evidence](evidence/ci-failure-cause/discarded-integration-fixtures).
They do not prove the CI timing race was reproduced. The unit reproduction and
code inspection establish the overwrite defect; hosted confirmation remains open.

An isolated frontend/package build produced a new development tuple member:

- Nexus wheel SHA-256: `d28a7a22cfa167a9598688fc7a31ace8e28eb484b5a901c6ff37be8b67dc6e91`.
- Nexus sdist SHA-256: `4394c1919ec7bb48984cc769e74b217e43b27079ac6ebe4b63f37163cba41e3f`.
- Core and Connector pinned wheels are unchanged.

After installation, **48 tests passed in 162.42 s** on Windows/Python 3.13.1.
The campaign verified package bytes against all three wheels and recorded unchanged
inputs. Coverage includes failure arbitration, provider-vault success/refusal,
embedded dispatch and renewal, shutdown storage ordering, uncertain ownership,
cancelled observers, HTTP shutdown and CLI shutdown over TCP.

[Campaign](evidence/ci-failure-cause/campaign.json),
[JUnit](evidence/ci-failure-cause/tests.xml),
[build manifest](evidence/ci-failure-cause/build-manifest.json), and
[installed artifacts](evidence/ci-failure-cause/installed.json).

## CI queue and remaining release work

Six queued installed-regression runs on ancestor commits were canceled after
checking their queued state and ancestry to `43aa8de`. All six cancellations were
confirmed terminal. They were superseded by cumulative corrections, not canceled
for elapsed duration; the latest run and campaigns already observed running were
retained. [Exact runs and confirmations](evidence/ci-failure-cause/nexus-superseded-queued-runs.json).

NS14 contention, the 100 ms boot-budget fixture, current full hosted regression,
dashboard completion, final immutable artifacts, independent-host/platform/provider
acceptance and G0–G3 remain open. This development build is not the final M13 freeze.
