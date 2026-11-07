# AC-08: final documentation, help and schema comparison

Recommendation: the reviewed final three-package surface supports AC-08 after the eight documentation corrections are committed. No ledger status was changed.

Only docs changed. Ten isolated Nexus help commands and one Connector parser import completed successfully; all 75 Connector parser blocks generated the exact replacement CLI reference. Six already retained service help reports were reused. No productive example, service, provider or credential was used.

| Surface | Result |
|---|---|
|Nexus service lifecycle|Aligned after removing obsolete upgrade-pending aggregate text.|
|Nexus connect and remote project setup|Aligned after replacing obsolete statements that participant initialization and remote bootstrap remain unimplemented.|
|Nexus participant lifecycle|No concrete doc/parser mismatch found; real two-client/provider participation is not inferred from these contracts.|
|Nexus work|Aligned after separating delivered onboarding/startup review from pending real-provider/native-login qualification.|
|Nexus coordination|No concrete mismatch found; no creation/observation command was executed during this audit.|
|Nexus attention API and UI|Contract aligned; removed obsolete future PR07 client wording. Existing behavior assertions and retained PASS references are included separately.|
|Nexus external observations and correlation|No concrete mismatch found in reviewed fields/endpoints/defaults. Correlation remains local Windows only as documented.|
|Connector connect/configure and lifecycle|Regenerated stale CLI reference; corrected reconnect interruption claim and obsolete upgrade-pending aggregate text.|
|Core API, participant format and published schemas|Completed API method reference; lifecycle contract was current. Core is a library with no new CLI requirement.|

The exact changed-file hashes, source/evidence references, preserved assertion-to-PASS mappings and published Core JSON resource comparisons are in `audit.json`. `doc-changes.json` retains before/after hashes; original public docs are under `before/`.

The existing HTTP planning schema stays classified as planning, not a complete published API contract. The short Connector help phrase “JSON optional” refers to the optional template; `--json` wizard output remains explicitly unsupported.

Real providers, native Task Scheduler mutation/login/logout, two physical hosts and actual two-client productive campaigns remain outside this audit. Historical test evidence is not claimed as a new run.
