# Resume catalog migration after reviewed adoption

The offline `admin migrate-execution` path now recognizes an adoption receipt
recorded in the same transaction as binding apply. The receipt binds the resulting
endpoint, generated profile and binding to their row digests. The original endpoint
digest remains attached to the immutable backup. Generated profiles are excluded
from subsequent legacy backfill so retries do not invent new legacy records.

Resume compares every preserved backup row, allowing only recorded endpoint
adoption and operational presence/owner fields changed by starting and stopping
the server. Writer contract installation may advance from 0 to 1; other contract
changes remain subject to comparison. A live dispatcher owner still refuses the
offline command before migration. Credentials, source profiles and other preserved
fields remain checked. New rows created by onboarding are permitted; preserved
rows cannot disappear. No migration invokes a provider or activates execution.

The directed test completes public operator-reviewed adoption, stops the HTTP
lifespan and repeats the offline migration twice. It checks stable migration maps,
disabled endpoint policy and the legacy profile, then separately changes the
endpoint, generated profile, binding, legacy profile, credential, absent receipt,
incomplete receipt or live owner and requires refusal. Missing receipts from an
older adoption are refused for review, not synthesized from current rows.

The initial source run used stale Core 0.2.30 and failed at import. Updating only
the environment to the repository pin 0.2.51 exposed the actual resume failure.
The fixture now issues both keys before backup and reuses them during onboarding;
credential comparison was not relaxed. The writer fence transition is handled
explicitly. Initial XML failures are retained alongside the final evidence.

The wheel is built in a temporary source copy with the three preexisting modified
HTTP assets restored from HEAD in that copy only. Installed verification compares
all three wheels to installed package bytes and Nexus runtime source to the wheel.
The original assets and historical document deletions remain untouched.

See `test_runs_20261001_migration_resume.json` for results and artifact hashes.
This is a partial NS15.01/M12 increment. Normative historical-job acceptance,
complete M0–M3 recovery, M4 cutover, coordinated rollback and release gates remain
open. The tests use a synthetic discovery candidate and do not qualify a provider.
