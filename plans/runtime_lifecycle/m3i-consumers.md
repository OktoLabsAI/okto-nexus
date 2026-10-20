# M3i: independent inventory consumers

Status: consumer checkpoint qualified; producer integration and joint UI gate remain open.

The Server now evaluates freshness for the binding's selected harness. A newer
observation of another harness cannot renew old evidence, and pending or failed
observations cannot authorize new execution. Admission, dispatch, lease renewal,
intent processing, session reuse, capacity and configuration paths use the same
Core observation contract with publication receipt and transport age checks.

An unchanged format-2 selection can migrate to format 3 without asking the user
to approve the same installation again. Pending/failed discovery preserves an
existing compatible consent baseline but does not grant execution. Previously
incompatible selections remain incompatible. Changed candidates, platform or
control evidence still require the existing review checks.

Runtime option projections expose coverage and freshness per harness; the UI
distinguishes discovery still running from an installation that is absent.
Local inventory wrappers accept the exact coverage used by a partial snapshot.
Producer and onboarding callers still need integration with retained published
batches before this contract is deployed globally.

## Validation

- Source consumer campaign: 64 passed; additional authority/wrapper cases: 10 passed.
- Exact installed Nexus wheel: 94 passed, no failures, skips or changed inputs.
- Exact installed Connector wheel: 36 passed; committed as `15e1d53`.
- Core independent observer foundation: previously qualified with 117 installed cases.
- Fresh dashboard TypeScript/Vite build and installed dependency check passed.
- Artifact hashes, file counts and campaign hashes: `m3i-consumers-results.json`.

The first source run exposed two incorrect fixture expectations: an unchanged
approved publication is intentionally accepted. The corrected fixture first
publishes changed evidence before asserting preservation of incompatibility.
The Connector's first isolated test collection lacked its declared websockets
dependency; installing it in the isolated environment allowed the final campaign.

No global rollout or new-feature UI gate occurred for this checkpoint. The live
installation remains generation 72 on Nexus M3j and Core M3h.

## Live recovering report, 2026-10-17

At 06:08:51 UTC the read-only database observation showed CONTROL_READY on
generation 72, all three local recovery records READY, four Pi WARM slots, no
warm backoff, and current session leases. The running instance's stderr contained
startup recovery completion and no subsequent recovery failure.

At 06:11:56 and 06:12:16 UTC both existing Chrome Nexus tabs displayed Pi, Claude
and Codex as Local Online with recent host contact. Neither page was refreshed,
and the server was not restarted. The user's all-recovering report was not
reproduced during this inspection; a stale UI is a hypothesis, not an established
cause. L12 remains open. This read-only incident inspection is not the M3i UI gate.

## Remaining

Integrate independent workers in embedded and Connector producers; retain the
exact published batch for selection; correlate refresh acknowledgements to
post-request observation frontiers; retain native work through shutdown; and
make initial runtime boot retry individual pending harnesses instead of waiting
on, or skipping them behind, a global readiness barrier. Then qualify both
installed paths and perform the joint real UI milestone.
