# P12 — exact coverage review and native frame evidence

2026-09-24, implementation/test source
`e388227f98c1230e8104df12b602e5943b4baf52`, feature/v0.2.0.
**IN PROGRESS; final gate NOT PASSED.** No application contracts changed in this unit.

## Source review and execution are different facts

`evidence/p12-coverage-review-e388227.json` maps original matrix stimuli to
specific assertions in test bodies. It currently covers 25 requirements, with
complete and partial coverage distinguished. This is source review, not a test
result. For example, the identity-preservation test opens/closes but does not
reopen, and the existing migration rollback test does not interrupt a nonempty
historical data backfill. Those aggregate requirements remain NOT_RUN.

Conversely, the slow-lane/backlog/per-agent scenarios explicitly required by
T-DISP-09 are now covered by the fairness and physical-worker tests. Extended
flood/delayed-handshake/crash sampling remains a separate P12/T-E2E-04 obligation;
it should not erase the narrower, actually tested guarantee.

`build_matrix_evidence.py` joins this manually reviewed coverage with completed
JUnit-derived manifests. It rejects mixed source SHAs, requires every selected
node and parameterized case to pass, preserves failures/errors, and does not
promote skips, absent nodes or incomplete coverage. It emits all 129 requirements
with generated counts. It does not silently overwrite the backlog or combine
historical suite totals with current execution.

## Full regression

Windows execution58066 remains in progress on the immutable source above.
Implementation and tests are frozen; only evidence tooling/documents changed.
The full command was:

```text
rtk proxy python -c "import os,subprocess,tempfile; from pathlib import Path; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN='',OKTO_NEXUS_CODEX_LIVE='0',OKTO_NEXUS_CLAUDE_LIVE='0',OKTO_NEXUS_UI_CAMPAIGN='0'); base=Path(tempfile.mkdtemp(prefix='okto-suite-e388227-windows-')); print('suite_source='+subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),flush=True); print('evidence_temp='+str(base),flush=True); raise SystemExit(subprocess.run(['.venv/Scripts/python.exe','-m','pytest','-q','--tb=short','--junitxml='+str(base/'results.xml')],env=env).returncode)"
```

Raw XML destination:
`C:/Users/jpamb/AppData/Local/Temp/okto-suite-e388227-windows-hclqag_s/results.xml`.
Do not restart this execution because an observation call times out. A complete
Linux run is planned after Windows, with no overlap between platform suites.
These suite durations are not a comparative performance benchmark.

`summarize_pytest_evidence.py` now accepts an explicit `--limitations` argument;
the historical hardcoded concurrent-platform note is no longer incorrectly
applied to every future report. Existing historical manifests remain unchanged.

## Content-free native frame instrumentation

`native_frame_campaign.py` runs the existing explicitly opted-in native tests,
using the installed executable and approved login-file path supplied by the
operator. The fixture retains ownership of isolated configuration and cleanup.
It does not change sandbox/approval policy, requests, native replies or scheduling.
It refuses dirty application/test sources (excluding protected generated assets).

Both adapters' existing stdout framing boundary and JSON writer are observed
before startup through final cleanup. Only known message labels, direction,
sequence, monotonic offsets and local identity aliases are retained. Bodies,
prompts, credential values, raw native IDs and arbitrary unknown protocol strings
are never serialized. The recorder has a finite100000-frame cap; overflow fails
qualification. Attempted writes and returned/uncertain writes remain distinct.
Outgoing unknown methods or status queries fail the no-polling qualification.
Control replies, steer and interrupt are classified separately. Driver reads of
Nexus operations are explicitly not classified as queries to the native harness.

This instrument itself does not establish native qualification. Fresh Codex and
Claude campaigns with these traces remain NOT_RUN until executed after the full
Windows suite. Previous actual native evidence remains the d76b78c campaigns;
Pi and dedicated attach native remain NOT_RUN under the user's configuration.

## Tool verification

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q plans/pr34-remediation/test_evidence_tools.py
```

13 PASS,0.10s. No subprocess/provider/network calls. Assertions include skip/error
handling, SHA mismatch, incomplete/missing nodes, parameterized-case completeness,
no sensitive content in frames, request/reply aliases, unclassified/status-query
rejection, bounded capture and uncertain write propagation.

Ruff initially reported E731 in the new report CLI; the lambda assignment was
replaced with a function. Subsequent:

```text
rtk proxy ruff check plans/pr34-remediation/build_matrix_evidence.py plans/pr34-remediation/native_frame_campaign.py plans/pr34-remediation/test_evidence_tools.py
```

PASS. The source inventory draft was removed after extracting reviewed mappings;
an AST inventory is not retained as if it were execution evidence.

## Next dependencies

### Additional reproduced security gap (T-AUTH-09/F13)

```text
rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/audit_backend_secret.py
```

Exit1, expected behavioral FAIL at e388227: a synthetic opaque credential
resolved from an approved profile `secret_refs` entry was echoed by an owned
Python Codex-shaped peer. Its literal value appeared in journal bytes, the
durable output and event replay. Evidence:
`evidence/p12-backend-secret-audit.json`. No provider, personal configuration,
real credential or external endpoint was used. The peer stopped and the
disposable home was removed. Existing credential-pattern redaction does not
cover arbitrary resolved secret values.

This is a correction to implement, not merely a missing test. Main source/tests
remain frozen while the full suite runs. A dedicated detached worktree was
created at `D:/Projetos/Techridy/okto_nexus_secret_remediation_worktree`, based on
e388227, for the narrow redaction regression/fix; it has no commits. All integrated
milestone commits/pushes continue only on feature/v0.2.0. Constructor/start/send
errors, streaming fragments and native approval content must be reviewed without
weakening correlation, pre-write proofs or journaling.

Finish immutable Windows regression; preserve and fix any failures. Execute
approved Codex/Claude frame campaigns and Linux regression with explicit
results. Continue review of the remaining matrix, add missing exact stimuli,
finish crash/pressure/comparative benchmarks and operational edges, then final
qualification and isolated build/reinstall0.2.0. No merge or final-gate promotion.
