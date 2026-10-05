# M05/M06/M09 - Native capability refresh

The automatic Pi composition in both consumers now reads current capability metadata before each native action. It retains the original secret, capability reference, scope and allowed actions. The response must name the exact lease ID and serial installed in Core. The local deadline is bounded by both the observed Server TTL (discounted for request time) and the installed Core lease.

The Nexus metadata callback verifies the live embedded owner and approved local configuration around the canonical capability service. The Connector callback reads the authenticated, nonce-correlated metadata route and checks approved local configuration around that read. Core validates the current session context before and after the domain effect through the existing ScopedNativeActionBridge. A lease change during metadata retrieval refuses the action before a domain mutation. Revocation, missing authority and a late response do not extend authority. A lost mutation response retains OUTCOME_UNKNOWN and the original operation ID.

The protected material is not reissued or sent to the Pi child. No Core contract, dependency pin or production qualification flag changes. Existing explicit factories without a metadata callback retain their fixed-deadline behavior.

## Verification

The canonical integration cases use real Server capability, lease and handoff transactions with installed Core. They exercise both transports after an applied renewal with an expired initial local deadline, lost response after commit, revocation, divergent scope, stale lease metadata and a concurrent lease renewal. They assert no domain effect for rejected metadata.

The automatic embedded Pi case uses public binding/grant/admission and the serve dispatcher. A technical native factory and in-memory vault isolate provider/OS dependencies. The test waits for automatic renewal and expiration of the initial metadata deadline, then invokes the composed owner's bridge for get/claim/complete and checks cleanup after public close. The Connector composition test invokes the bridge returned by its approved launch provider and verifies the metadata query.

Final installed results: 58 Nexus cases passed, 49 overlapping cases passed without Connector, and 81 Connector cases passed. Both environments passed pip check.

The final installed results, wheel hashes and exact commands are in test_runs_20260930_native_refresh.json. The isolated campaign verifies that neither the Connector module nor distribution is installed. Each runner compares source, wheel and installed package bytes before testing; all consumers use the same existing Core wheel.

Development failures were confined to the new Pi test fixture: its candidate stayed Codex, producing no Pi owner. A generic patch also touched a second fixture occurrence; review restored that occurrence. The corrected fixture and both automatic composition tests passed before packaging. The first installed campaign then exposed eight restart tests calling the fixture directly without its new request argument. Those three direct call sites now pass None explicitly; initial XML/logs are retained under native-refresh-initial-*. The final installed campaign reruns all selected cases after this test-only correction.

## Remaining acceptance

Real Pi/Codex/Claude provider journeys, live tool-configuration recovery, material-loss recovery, approval/input, platform/pressure, UI/CLI, migration and final release qualification remain governed by the fixed delivery plan. This increment closes the initial Pi deadline defect; it does not close a milestone or release gate.

Preexisting user UI bytes remain in the Nexus wheel and outside this change's UI acceptance. The existing Starlette/httpx warning is unchanged.
