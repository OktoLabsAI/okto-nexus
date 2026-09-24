# PR34 remediation — current execution state

Branch: `feature/v0.2.0`; version: `0.2.0`.
Implementation source: `ff905c433e1a92ae35993b2189919f75ad07dd51`.
Last published milestone: `336357a` (plan instrumentation and evidence only).
Final gate: **IN PROGRESS**. No merge performed.

## Active runs — resume these, do not start duplicates

- Windows full regression: tool handle `49697`, frozen detached candidate based
  on `39c5e6c` plus five corrections. Authoritative private launcher:
  `.git/pr34-evidence/final-candidate-windows-launch.json`.
- Linux full regression: tool handle `19457`, clean `ff905c4` checkout on WSL
  native filesystem. Launcher:
  `.git/pr34-evidence/full-ff905c4-linux-nativefs-launch.json`.

Both logs/XML persist under the recorded private run directories. Neither run
has been declared PASS. Keep their source frozen until terminal. Their overlapping
elapsed times are not performance measurements.

The Windows candidate and integrated commit have normalized-source equivalence:
543 files, 12 exact byte matches, 531 CRLF-only UTF-8 differences, zero other
changes or candidate mutations. See [source qualification](P12_CORRECTED_RELEASE.md).
Do not replace the original base/diff identity with a fabricated committed SHA.

## Completed qualification

- Five corrections integrated and pushed at `ff905c4`: grouped ordinary read
  receipts restored alongside operation-specific external ACK proof; migration
  expectations updated through64; Claude event notification tested directly
  instead of conflating process startup with a tight latency threshold.
- Integrated focused regression7 PASS and isolated real MCP smoke PASS. Prior
  failing full suites and all correction evidence remain in
  [receipt regression](P12_RECEIPT_GROUPING_REGRESSION.md).
- Approved installed Codex7 PASS and Claude stream6 PASS on `ff905c4`, terminal
  exit0; no outbound native status queries, trace overflow or unclassified frames.
  Fresh copied credentials removed. [Native evidence](P12_NATIVE_FRAMES.md).
- Corrected candidate dashboard15 PASS with sandboxed isolated Edge; Linux browser
  NOT_RUN. [Dashboard evidence](P12_CURRENT_DASHBOARD.md).
- Corrected wheel/sdist built from clean archive, fresh frontend,64 migrations,
  lock and actual Twine checks PASS. First Twine import preparation failure retained.
  Artifacts and hashes: `evidence/p12-release-ff905c4.json`.
- Operational metric probes passed Windows/Linux with10 observed fixture turns
  each and no owned processes remaining. Three integrity tests/platform passed.
  [Metrics and limits](P12_OPERATIONAL_METRICS.md).
- All129 requirements have reviewed verification routes; catalogue alone is not
  an execution or acceptance promotion. Backlog currently126 scoped PASS/3 NOT_RUN.

## Pending work in dependency order

1. Observe both full suites terminal; reduce persistent XML and investigate any
   failures. Preserve original run/source identity and skips.
2. Join current full/native/browser results with the129 reviewed routes; refresh
   changed test hashes, retain scoped crash/load evidence and final comparison.
   New plan-only `join_release_evidence.py` and integrity tests are being qualified.
3. Finish finding→code→evidence, task/phase statuses, operational readiness report.
4. Recheck installed-tool process census/storage and reinstall the corrected
   wheel locally, preserving Python/serve extras and compatible dependency pins.
   Global install remains0.1.10 until this step; never open/migrate the personal
   database merely to validate installation. Run isolated installed-package smoke.
5. Commit/push remaining milestones only to `feature/v0.2.0`, verify remote state,
   and report qualified scope plus external limitations. No automatic merge.

Pi native remains NOT_RUN by user decision. Dedicated Claude attach native remains
NOT_RUN without an approved dedicated session. These also limit three-native
concurrency and dedicated-attach gates; fixtures do not qualify those protocols.
No unnecessary repeat of completed real-provider campaigns.

## Protected local work

Do not stage or overwrite the three pre-existing modified generated HTTP static
assets or `.nexus-policy-guardrail-test/`. Release builds use clean Git archives
and temporary frontend output. Windows fixtures use private temporary directories
on D; do not commit raw logs/XML with fixture credentials. No personal files were
deleted to resolve the earlier C-drive capacity incident.

## Authoritative records and history

- [Backlog](../../05_BACKLOG.json), original specs01–06 at repository root.
- [Final audit in progress](P12_FINAL_AUDIT.md).
- [History through336357a](IMPLEMENTATION_HISTORY_TO_336357A.md) preserves the
  previous status verbatim. Old pending labels/handles there are historical.
- [Earlier history](IMPLEMENTATION_HISTORY_TO_AF53F82.md).

Every published unit retains its exact source identity, commands, observed
results, preparation failures, limits and next dependency. Historical counts are
not summed into current execution results.
