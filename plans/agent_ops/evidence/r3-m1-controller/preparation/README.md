# Finite M1 controller preparation

The final installed synthetic integration passed **14/14 cases**. This validates
the preparation components; real M1 execution, provider inference, personal
credentials, Connector network topology and OS service behavior remain outside
this qualification. No actual campaign execution is authorized by this artifact.

## Operational use after separate campaign authorization

1. Keep checkpoints in the exclusive campaign root. Construct
   `Controller(path, campaign_root, create=True)` once; restore with `create=False`.
   Its lifetime file lock excludes a second controller. Always call `close()`
   in `finally` after monitoring and owned cleanup; closing the controller only
   releases its lock and does not stop a runtime.
2. Supply the existing bounded authenticated HTTP transport, persisted
   TerminalWork save/load callbacks and connection document. Wrap that transport
   in `FiniteResponseLoss(http, load, CampaignState(...), lane)` if the finite
   response-loss case is selected. Attach the resulting TerminalWork with
   `attach(lane, flow)`, and attach the exact owned home/service stop capability
   with `attach_owner(lane, home, stop_callback)`. See the synthetic fixture in
   `test_controller.py` for concrete composition.
3. Call `setup(id, lane, home, dispatch, stop_callback)` **before** the existing
   setup request; it persists the global reservation before invoking dispatch.
   Use `work(id, lane, text, stage=...)` for productive work. Six global reserved
   requests include setup and continuations. Never submit outside these gates.
4. Poll `poll()` at intervals **no greater than one second**, concurrently with
   any pending setup response. Retain and continue monitoring old sources for
   late usage. Stream/thread binding follows canonical events and preserves the
   same intent/operation IDs; response-loss reconciliation uses canonical GET.
5. After a crash, restore the same checkpoints and IDs, reattach flows and stop
   callbacks, and call `attach_setup_stop(id, home, callback)` for pending setup.
   Do not erase reservations or resubmit an uncertain request. An orphan pending
   checkpoint or unavailable capability requires reconciliation before dispatch.
   Unknown work without a resolvable session selects only its own owner stop.

At 100k observed tokens, missing/malformed/gapped usage or an unsettled 120-second
deadline, the controller blocks new work and selects the known work's canonical
interrupt/close or the exact owned service stop. Persisted stop selection is not
an OS-exit receipt; retain canonical status evidence. A failed/uncertain stop
does not authorize retry or bypass. Polling and bounded callbacks remain caller
responsibilities. The 700k tolerance is not an atomic or billed-usage guarantee.

## Retained evidence

`summary.json` and `manifest.json` identify final bytes and all three rounds.
The first round is diagnostic/intervened and wholly unaccepted; the next passed
13 cases; the final passed 14, including the unreleased-slot negative. All XML,
statuses and before/after input hashes are retained. Private test databases and
checkpoints are excluded. See [DETAILS.md](DETAILS.md) for source contracts,
namespace attribution, close/slot proof and qualification boundaries.
