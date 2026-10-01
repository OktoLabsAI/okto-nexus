# Preserve the legacy endpoint fence during canonical binding preparation

The existing alias-conflict lookup compared a legacy endpoint's adapter ID with
the canonical Core ID directly. After catalog migration, `codex` and
`codex_app_server` did not match. Omitting `adopt_endpoint_id` could therefore
produce an applicable fresh binding proposal beside an unresolved legacy endpoint.
Two reproduced failures cover an active session and an `outcome_unknown` session.

The lookup now also consults the endpoint's canonical adapter reference in
`execution_migration_map`. It reuses the recorded migration translation instead
of adding a second adapter-name map to runtime code. The existing proposal/apply
gate then requires review; explicit adoption continues through its session and
source checks. The original endpoint and uncertain session are never rewritten.

Tests require a non-applicable proposal, HTTP 409 on apply, zero new bindings,
one original endpoint and the unchanged session state. Reviewed adoption and the
normative historical M0–M3 acceptance remain covered by installed regression.
An initial test preparation assumed an unexposed `blockers` field; its failure
is preserved separately from the two actual `can_apply=true` reproductions.

This closes a cutover admission bypass, not full TR4-15-02. Its remaining proof
must combine real legacy-owner drain/observed stop, retained uncertainty,
refused replacement and safe rollback behavior. M12 and release gates stay open.
See `test_runs_20261001_migration_cutover.json` for installed results and hashes.
