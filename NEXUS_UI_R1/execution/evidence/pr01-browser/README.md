# PR-01 shell — browser qualification

Seventeen scoped checks passed: eleven main checks and six flag/auth checks,
plus an observed real cross-origin403. Read `qualification.json` for the exact
coverage and untested boundaries. This is qualification of the simplified shell
on the existing classic Home, not delivery of the new unified Home or onboarding.

Two final own GET-only loopback variants served the actual compiled
`index-6o2k3pzt.js`/`index-CqPDZl5S.css`. The standard HOME seed was reused; two
valid pending approvals were created through ApprovalService.intercept in the
disposable DB, never approved/executed. An informational delivery to operator
exercised the existing localStorage seen marker. No user DB/profile/provider,
native runtime, login, Narrator or mutation was used. All recorded API responses
in the main browser run were200; pageErrors/consoleErrors/mutation requests0.

The main run shows five sidebar destinations and four Advanced groups, the
Policies breadcrumb, MemoryOFF, global4 versus project3 attention, two global
approvals, independent queue filter/project selector, one canonical approval
dialog, Conversations seen semantics, and keyboard navigation at360px without
required horizontal overflow. The flag variant shows MemoryON, AttentionOFF
with the still-operable bell and canonical approval fallback. Actual HTTP
middleware denied an invalid credential401 and foreign Origin403. The latter
is a cross-origin trust test, not a delegated-agent authorization test.

The raw main output includes the observed mobile active element and explicit
menu-control hit-test; it does not prove an automatic focus transfer after the
menu animation. Dirty-form guards, every Advanced destination, native questions
arriving live, session targets, zoom/AT/human assessment and new onboarding
remain outside this run. No fake POST success or intercepted GET payload was
used. T-NAV-08's precise new-question setup and the unimplemented half of
T-NAV-10 must not be promoted from this approval proof.

Preceding finite attempts are retained: an implicit-label selector timeout,
the legitimate transient stale4* badge, waiting for real info feature flags,
and an assertion's text case. These are test preparation corrections; no
product source was changed. The final raw flag HTTP check stores status401
in its data field; qualification makes that result explicit rather than
counting the numeric status as an unrelated scenario state.

All own browsers and fixtures closed normally with terminal0 and PID absence;
all three ports had zero listeners after cleanup. See qualification cleanup
records and runtime READY import pins. Source/bundle/script hashes qualify the
frozen working tree. Product version is0.3.5; no release or campaign approval
is inferred. No ledger was modified by this probe.
