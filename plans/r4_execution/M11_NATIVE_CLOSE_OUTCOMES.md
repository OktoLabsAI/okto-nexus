# M11 — Confirmed native close outcomes

Core 0.2.32.dev0 records whether Codex/Claude cleanup requested process termination. The adapter reports graceful or forced only after owned-tree stop is confirmed; the bridge independently observes stop before accepting that result. Unconfirmed stops remain unknown. This corrects the repeated real-provider close ambiguity recorded in the preceding campaigns.

Both consumers pin the same wheel: SHA-256 `a32d49400c0e22ccedd1fbe7f26b8f74ff0b3bb2d55f21eac469dd0ae8a8784f`. Source, wheel and installed package bytes are compared by the installed runner.

## Real provider evidence

Codex 0.159.0 and Claude 2.1.282 opened under locally installed R4 grants, completed successful correlated turns and accepted close with no receipt error. Their subsequent shutdown reported already_closed. Codex shutdown during the long-turn probe returned forced within 4.13 seconds and refused later submit.

The close receipt remains SUBMITTED; terminal close publication is not proven by this increment. The long-turn shutdown probe does not independently prove active generation at its fixed delay. Server-issued authority journeys, remaining close/crash scenarios, Linux and independent hosts remain pending.

## Tests and scope

Fifteen focused tests exercise EOF, forced timeout, prior force, tree-stop proof and bridge classification. The full installed Core, Connector and Nexus campaign results are recorded in [the coordinated manifest](test_runs_20260930_native_close.json). The same runner verifies all three installed products before running tests.

No milestone or release gate is closed. Renewal/reconciliation and the remaining M00–M13 requirements continue under DELIVERY_PLAN.md.
