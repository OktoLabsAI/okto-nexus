# Sonnet successor: offline candidate only

The user's proposed cumulative 500,000-token allowance remains pending. The currently authorized allowance is 200,000. No authorization record, selected work plan, derived approved seed, paid namespace, service or provider call was created by this preparation.

The original sealed checkpoint restores exactly 144,004 tokens and two charged admissions. The previous useful attempt was canonically terminal but its useful result was not confirmed. The two historical rows remain byte-equivalent as JSON values, including all events, charges, outcomes and original ledger policies; no refund or settlement is inferred.

The existing reserve formula gives 244,846 tokens for the next request, so 144,004 + 244,846 = 388,850 refuses admission under the current allowance. The proposed policy is cumulative 500,000 / preventive 480,000, with at most two new requests (four total). This is not an atomic provider token-cap guarantee. Continuation must pass the same actual headroom check again.

New IDs are `m1-sonnet-remote-useful-05` and `m1-sonnet-remote-continuation-06`. Previous IDs and unused conditional continuation04 are ineligible. The existing canonical useful/new-session flow, exact immutable profile binding, native permission review, observation/interrupt/normal-stop behavior and same-session continuation are reused.

`successor_policy.py` requires root's local record of the actual explicit user response to the pending budget question. The user does not need to type hashes, sign a file, or answer an additional question. No real record is included. Synthetic approvals exist only inside unit-test memory.

The candidate adds a sealed budget v2 with explicit cumulative limit/max_requests. It reads v1 checkpoints with their original default200k/max3 and verifies their original seal. Historical rows keep their old policies; new ledgers use the selected policy. `work_context.py` checks approval before constructing any lifecycle context, and verifies that its seed is exactly the authorized derivation of the original checkpoint.

`select_plan.py` is a future offline composition command. It requires the actual authorization record and a root-reviewed fresh package/cohort composition. It rejects reuse of the old restart plan or old installation context. It does not construct a live Context, start services or call a provider. The composition must retain existing binding/rotation/DONE ancestry and supply fresh watcher receipts, prior physical cleanup evidence and a qualified corrected package. These actual prerequisites do not exist in this candidate; the command has not been executed.

The following commands are preparatory/future steps, not instructions to execute now:

1. Root records the real answer, if approved, in `authorization-record.json` with `explicit_user_approval`, literal `user_response`, `response_reference`, the proposal SHA, policy `{limit:500000, preventive:480000, max_requests:4}`, carry144004, charged_requests2, new_requests_max2.
2. After authorized cleanup/package/lifecycle work, root supplies `fresh-composition.json` with the exact pinned canonical bindings accepted by `select_plan.py`. Its reviewed SHA is the argument, not a user approval requirement.
3. Run the `select` argv in `commands.json`. Review the resulting work plan before selecting any provider action.
4. With the corrected installation's Python, run the inherited entry `prepare`, then `useful`; inspect native permission requests individually. Select `continuation` only after useful success and the runtime's fresh budget/session checks. No setup or lifecycle start is implicit in these actions.

Six offline tests passed using the existing R installation Python. They cover sealed carry/history tampering, pending/mismatched authorization, unchanged historical rows, current200k refusal before reservation, replay/total4 and continuation/effect boundaries. No new package, actual approval or live campaign is claimed. Old frozen sources/checkpoints are unchanged.
