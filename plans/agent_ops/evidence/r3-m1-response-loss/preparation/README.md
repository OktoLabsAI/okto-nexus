# Finite M1 response-loss preparation

This is client instrumentation in Temp, not a product change and not a productive
M1 runner. It wraps the existing decoded operator callable used by TerminalWork.
It does not receive authentication headers, proxy provider traffic, start native
processes, configure services or retrieve credentials.

## Executable synthetic validation

Run with the pinned installed environment:

```text
C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe -I run_synthetic.py
```

The only optional argument is `--crash-check`, which selects the two deterministic
crash-boundary cases. Every run creates a fresh `synthetic-run-*` directory. The
runner records hashes before/after for 992 installed product and tooling files,
checks the five copied fixture hashes, checks loaded product module locations,
and retains JUnit XML plus status. Test data/SQLite/homes are private, excluded
from the public allowlist.

The installed integration uses actual Nexus ASGI routes, canonical SQLite,
TerminalWork and embedded Core with a synthetic native executor. It is not the
Connector network topology. Popen and Windows credential operations are denied
by test guards. A synthetic admission is discarded only after its actual
canonical response, then a reconstructed TerminalWork recovers the same session
and operation. A synthetic approval decision is discarded only after its actual
canonical CONFIRMED response, then a reconstructed TerminalWork recovers the
same decision. Assertions require one work POST, one decision POST, one native
synthetic turn, one native synthetic reply, one session, one turn.submit row,
successful result and canonical close. Canonical decision confirmation is not
misrepresented as a provider's execution ACK.

## Driver interface

Create `CampaignState(path, campaign_id=...)` once with an absent file. Restore
with `CampaignState(path)`; never create another campaign file to bypass spent
reservations. Share one state object between the two allowed lane labels,
`local` and `connector`, in a single serial controller.

Construct `FiniteResponseLoss(existing_operator_call, checkpoint_load, state,
lane)` and give that callable to the installed TerminalWork. Use the product's
existing checkpoint saver. Arm an admission fault with exact client_intent_id,
or a decision fault with exact canonical approval_id:

```python
state.arm('admission', 'connector', original_client_intent_id)
state.arm('decision', 'connector', actual_canonical_approval_id)
```

Each fault can be armed once per campaign. The installed product PREFIX is used;
only the exact POST operation/approval-decision routes can be faulted. Durable
checkpoint identity/scope is checked before forwarding. Only matching confirmed
responses are discarded. The caller receives `ConnectionError(OUTCOME_UNKNOWN,
possible_effect=True)`, while the spent fault survives reconstruction.

The wrapper reserves before sending and rejects repeat POSTs; recover via the
existing canonical GET/resume paths. If a process exits with a `forwarding`
reservation, or an actual response/transport is unconfirmed, new work/decisions
remain blocked. Inspection and canonical interrupt/close remain available.
There is deliberately no automatic reset, retry or reconciliation override.
These exceptional cases stop this finite campaign for explicit inspection.

The journal contains identifiers, phases and decision_id only: no prompt,
answer, raw response, CAS token, headers or credentials. It is private campaign
state, not a replacement for canonical receipts or the product checkpoint.

## Finite limits and remaining integration

The wrapper caps six productive POST reservations and two decision POSTs across
its two lane labels. This counts only calls traversing this wrapper. In
particular, a Server-side setup:test can consume inference without traversing
these routes in this client. Therefore this wrapper alone does not enforce the
whole campaign's six-admission allocation or token budget.

Before any real campaign authorization/execution, the outer runner still needs
to combine this driver with the separate token collector: arm before setup,
discover/replay fresh owned setup sessions from sequence zero, reserve all setup
and work admissions, enforce serial active work, honor the existing preventive
100k threshold/deadline, and issue only the owned canonical interrupt/close.
No hard aggregate token cap is claimed. The 700k proposal does not authorize
provider use or make this integration complete. No new product feature or
acceptance requirement is introduced here.

## Retained validation history

1. Initial: 8 deterministic cases passed; installed setup errored before app
   creation because replacing Popen by a function broke the SDK type annotation.
   Guard changed to a subclass that rejects construction.
2. Next: 8 deterministic cases passed; installed case found the driver route was
   missing the actual `/api/v1/runtime-management` prefix. Fixed by importing
   the installed product PREFIX, rather than guessing a route.
3. `synthetic-run-a2o99mdo`: 9/9 passed, 992 inputs unchanged, no product shadows.
4. Root review found a crash boundary: a persisted forwarding reservation could
   otherwise admit a distinct request after restart. The guard now fences all
   forwarding/unconfirmed records. Only the two new cases were run afterward:
   `synthetic-run-oziznf0y`, 2/2 passed, 992 inputs unchanged, no product shadows.

5. `synthetic-run-ncmurvj3`: all 11 distinct driver cases passed together on the
   final bytes, including the installed integration and both crash boundaries;
   992 inputs unchanged and no product module shadows. This targeted final
   requalification was requested because the crash guard changes a shared path.

The final qualification is 11 distinct passing cases, not a sum of executions.
Neither passing suite qualifies M1, a real Codex login, paid inference, actual
native approval or Connector delivery. No repository file was changed.
