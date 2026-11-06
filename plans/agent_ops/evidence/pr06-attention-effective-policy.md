# PR-06: effective Server policy episodes

Effective Server policy now has durable generations for harness integrations and HITL. Only the owning Server lifespan and committed settings activation publish effective values; CLI/env pins, equal-value writes, restarts, rollback and resets preserve their intended semantics. Attention reads policy values and generations in one snapshot and uses them only for responsible denial gates; same-clock recurrence does not inherit seen/snooze, and irrelevant toggles preserve independently revoked-grant episodes. 403 distinct installed cases passed on Windows with zero skipped. The Windows open-SQLite-file unlink test also fails on the previous installed wheel; it remains a recorded limitation and is explicitly deselected in the installed policy group, never counted as passed. Migration 163 is additive, and migrations 161/162 remain unchanged. PR-06 client reconciliation and PR-07 UI/browser acceptance remain open; no real-provider/client/native-service or full R3 acceptance is claimed.

## Implementation

Migration 163 stores only two effective boolean values, generations and UTC change timestamps. It starts empty; no override is mistaken for an applied policy. First publication is a durable observation, not invented prior history. The owning Server validates the same OS lock generation, home and database; incidental bootstrap and unowned app construction cannot publish. Both reset modes retain metadata.

Settings persist policy in the same transaction and apply their in-memory cache only after COMMIT, before the next writer is admitted. Failed SQLite COMMIT, explicit rollback and late errors discard cache updates. Finish still stages the override separately and activates the latest committed policy through its existing refresh/recovery path.

Attention reads effective values and generations in its existing snapshot query. Denial generations are used only after independent canonical authority gates have been examined. Native decisions also reflect the existing HITL dispatch gate. Historical handoff episode identities and constant SELECT counts remain covered.

## Qualification

The installed wheel SHA256 is `bdf80e88d239c362d62e034e44c2ee6d51d40dd21252e7a9bbe52aad77387628`. All 478 Python files, 7 static assets and 163 migrations match working source, wheel and installed bytes. Tests run outside the checkout under isolated Python imports, with Core 0.0.14 and Connector 0.0.12. Distinct installed testcase identities are counted once; repeated source runs are not added to that number.

Source and installed reports retain initial failures and exact original/artifact hashes. Synthetic API-key-shaped secrets are redacted before retention, and XML-preserving normalization is checked. See [reports](pr06-attention-effective-policy-reports.json) and [wheel payloads](pr06-attention-effective-policy-wheel.json).

The initial authority tests used the active filter after snoozing; the corrected assertion reads all states. A later diagnostic run identified a fourth SELECT; policy metadata was folded into the existing defaults query. That diagnostic file also loaded a test before a later test-only addition and is explicitly excluded from final qualification. Final source and installed runs used frozen files.

The initial installed attention suite passed 272 cases and failed 13 old upgrade assertions expecting schema 162. The corrected tests explicitly expect 163, require an initially empty effective-policy table and preserve their canonical data, viewing preferences and rollback assertions. Only these affected test files were rerun against the unchanged installed wheel. The integrated HTTP test also corrected an overly broad HITL expectation: an ordinary turn without native-request requirements remains authorized, while its pending native decision is blocked.

One existing connection-pool testcase attempts to unlink an open SQLite database. Windows rejects this with WinError32 on both the changed source and the previous installed wheel. Both failures are retained; the installed policy group explicitly deselects this testcase. It is not a pass, skip, or policy acceptance proof.

## Limits

The fixed plan is unchanged. Browser reconnect, UI accessibility/canonical navigation, real provider/client campaigns and native user-service campaigns remain outside this increment. No personal credentials, provider inference, service registration, merge or package publication occurred. Connector and Core are unchanged.
