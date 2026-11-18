# SI-011 dashboard interrupt for an exact Codex turn

Under the opt-in interaction gate, an authenticated human can resolve a current interrupt target and submit it through R4. The target is drawn from the exact session's committed Codex start event and matched active operation and opening thread. The current scope, owner generation, connection receipt, stream continuity and selected build all participate. A missing, ambiguous, superseded or terminal target leaves the control unavailable.

The admission transaction checks the same target and queue revision and installs the durable queue barrier with the interrupt operation. The dispatcher rechecks the operator login and target before the send cut. Core receives the same native turn ID. Querying the original client intent recovers its receipt under the original login and exact session. A repeated submission recovers the same operation. Receipt lookup performs no admission.

## Evidence

- An embedded application test using a synthetic Codex peer made the target available only after the authenticated start event committed. A different native turn or owner generation did not resolve. The target became unavailable after the canonical terminal event.
- The authenticated HTTP scenario refused a different target and stale queue revision without installing a barrier. The accepted request installed the barrier before the synthetic peer received the exact interrupt. Receipt recovery and repeated submission returned the same operation. A different login could not recover it. Validation and foreign-origin requests were refused.
- The older R4 send-cut regression now verifies that a pending interrupt keeps the barrier. Its test marks the synthetic control terminal before resuming and verifies that recovering the old interrupt does not reinstate the barrier.
- The combined execution, dispatch pump, containment and interaction run passed 116 Python cases. The offline lock check passed. The Nexus 0.3.8 wheel and source archive passed Twine's strict check. Five entries matched their current source bytes, including the target resolver, control API and dashboard bundle. The temporary wheel's SHA-256 is `e25e3122fdbfeffaac8ee151b2506f24319aebc15c22453c015a540cfc09378d`.

## Delivery and rollback

The API and dispatch checks use the existing schema. A source rollback must preserve the durable pause and let compatible runtime readers reconcile any retained operation. The dashboard panel, native interruption confirmation, Pi and Claude observed-run targeting, and the real remote and harness qualification campaigns remain pending.
