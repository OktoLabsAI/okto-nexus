# Restricted monitor credentials and anonymous stdio acceptance

2026-09-24, feature/v0.2.0, parent9df5b3983a0663aa2b3e72819eb516a8a4c8a08d.
New test_runtime_monitor_authorization.py closes exact transport-level gaps
found during T-AUTH-08/11 review; it also checks control denial parity and
opaque, audited refusal for a read-only delegated actor.

The actual production socket app issues a real disposable EPT through its
existing service. Events/cursor and inbox/count succeed, proving the credential
is valid. Runtime open/send/steer/interrupt/close, session/event/endpoint reads,
and MCP control access return AUTH_FAILED, with zero commands and zero peer
writes/spawns beyond the explicitly opened fixture session. EPT failures occur
in credential middleware before runtime access auditing; no fictitious runtime
audit record is claimed for those rejected credentials.

A narrow runtime read/events grant permits reads over both REST and MCP, while
open and all four controls remain denied. Real and nonexistent session IDs
produce identical refusal envelopes on each surface. The authenticated caller's
denials are persisted for every control action. Existing positive granted sends,
budget limits and authenticated real stdio are included in the expanded gate.

The anonymous case starts an actual Nexus stdio process with explicit feature
ON, an isolated home and an allowlisted environment without an API key. Open,
send, steer, interrupt, close and get are denied, leaving the real owner's
session count unchanged and no runtime commands. The approved Pi profile points
only to the local Python interpreter with the required Pi argument suffix; it
cannot launch an installed model/provider if denial were broken. The parent
owner uses the synthetic external peer. The Python executable would reject those
Pi arguments if mistakenly launched; that is not an authentication success.

## Execution history

- Initial Windows10052:2 PASS/1 FAIL10.10s. Test profile used --version, which
  correctly failed the required native argument contract. Fixture corrected to
  --mode rpc; product validation was not relaxed.
- Windows90565:3 PASS12.01s, one existing Starlette/httpx deprecation warning.
- Added full REST known/missing refusal equality before the expanded gates.
- Windows78373:21 PASS61.71s / Linux59377:21 PASS75.62s, both exit0 and one existing Starlette/httpx deprecation warning.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/monitor-9df5b39-windows.xml tests/test_runtime_monitor_authorization.py tests/test_runtime_grants.py tests/test_poll_tokens.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/monitor-9df5b39-linux.xml tests/test_runtime_monitor_authorization.py tests/test_runtime_grants.py tests/test_poll_tokens.py
```

No production correction or native provider invocation. Fixture failure is not
a product RED. Source/tests frozen while selections run. Persistent XMLs will
be reduced to sanitized per-node manifests with explicit new-file hash. This is
not a full matrix, all-authorizations, load, benchmark or final release gate.


Both persistent XMLs were found and reduced to sanitized per-node manifests
p12-monitor-windows.json / p12-monitor-linux.json. Each mapped requirement node
and parameter was required to exist and PASS on both platforms. Explicit parent
SHA/new-file hash prevents presenting this as a clean immutable full run. The
mapping is p12-monitor-authorization.json. Ruff PASS; no live processes remain.

T-AUTH-01/02/08/11 scoped acceptance PASS. Remaining authorization axes, native
campaigns and final gates are not implied. The default reducer native-flags label
was replaced with the exact selected-fixture scope, rather than claiming flags
that this command did not set.

Reduction command for PLATFORM=windows or linux:

```text
rtk proxy python -X utf8 plans/pr34-remediation/summarize_pytest_evidence.py .git/pr34-evidence/monitor-9df5b39-PLATFORM.xml 9df5b3983a0663aa2b3e72819eb516a8a4c8a08d PLATFORM plans/pr34-remediation/evidence/p12-monitor-PLATFORM.json --limitations "Parent SHA plus new test-file hash; actual restricted credentials and stdio, synthetic external peers. No native provider campaign. Not a full suite or performance benchmark."
rtk proxy ruff check tests/test_runtime_monitor_authorization.py
```
