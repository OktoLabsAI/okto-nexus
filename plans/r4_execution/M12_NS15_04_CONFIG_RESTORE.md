# NS15.04 configuration migration and post-effect recovery

TR4-15-04 exercises two normative cases: selected configuration apply/retry and
joint offline restore after a possible native effect. Configuration publication
uses a flushed temporary file and atomic no-replace link, so a failed apply does
not leave partial target bytes. Exact owner markers/digest paths remain required;
a foreign binding marker is refused without changing it or its configuration.
Selected MCP migration retains its original backup, unrelated entries and CAS.

Version 2 of the existing offline recovery procedure includes the Server's
embedded Core SQLite journals/slot ledger and owned session configuration along
with the Nexus DB, legacy journal and artifacts. SQLite backup folds committed
WAL into each copied database while source exclusion locks remain held. The
validator checks opaque SQLite integrity without reading Core-private schemas,
requires journals referenced by Nexus local stream records, and validates the
owner digest/scope of copied session homes. Snapshot inspection uses immutable
Core database readers; an initial test caught WAL side files created by ordinary
read-only validation, and the corresponding failure evidence is retained.

The post-effect case invokes actual local admission/dispatch/Core with a synthetic
native peer. The peer records one send and loses its outcome. Server dispatch
retains RECONCILING with possible_effect=true and retry_safe=false; the test does
not invent a terminal Core receipt. Backup refuses the live owner. After owner
shutdown, restore preserves all canonical operation, receipt, dispatch, event,
watermark and session rows plus Core journals/configuration. Public history is
available with execution disabled, and no replacement native effect occurs.
Restore without explicit quiescence acknowledgement, overwrite of the original
home, and omission of a referenced Core journal are refused.

The [operator runbook](../../docs/harness-integrations/migration-and-recovery.md)
distinguishes failed pre-effect apply, post-effect drain/reconciliation and
explicit restore. Active paths/markers are never moved or rewritten. Credential
stores, ambient provider homes and remote Connector stores are deliberately not
represented as included in a Server snapshot; their owners must be quiesced and
preserved separately before coordinated recovery. This campaign qualifies the
Server migration layer, not real-provider, Linux or multi-host release acceptance.

Evidence: `run_ns15_04.py`, `test_runs_20261001_ns15_04.json`, and the
`evidence/ns15-04-*` installed artifact/test records. Task dependency acceptance
and final M13 provider/platform/release gates remain open.
