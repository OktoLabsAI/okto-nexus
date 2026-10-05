# Real embedded providers with executable R4 — 2026-10-02

The installed development tuple from `r4-053-conformance/installed.json`
completed two actual Windows provider journeys over local HTTP MCP:

| Provider | Result | Duration |
| --- | --- | --- |
| Codex 0.159.0, exact qualified binary | PASS | 133.65 seconds |
| Claude Code 2.1.282, exact qualified binary | PASS | 94.24 seconds |

Both opened a real native session, observed lease serial >= 2, completed the
canonical handoff through actual MCP tool calls, handled three explicit operator
decisions, closed successfully, and removed the temporary tool secret. Each
recorded one tool claim and zero WSS link tickets. No readiness or native
qualification override was used; no synthetic native factory was installed.

The currently installed user Codex is 0.159.3 and was refused with
`NATIVE_VERSION_UNQUALIFIED`. That failed campaign is preserved. Codex 0.159.0
was then installed under a separate temporary npm prefix with scripts disabled;
the user's installation was not replaced. The recorded fingerprint and portable
identity match the Core's existing exact qualification.

Tests were staged outside the checkout while the full regression's inputs
remain frozen. Compared with their recorded source hash, they replace readiness
monkeypatches with assertions, mark the report override false, and select the
isolated qualified Codex path. Candidate source, JUnit, logs and provider facts
are retained in each directory. The Claude campaign's generic runner scope
label was corrected explicitly; its node ID and provider facts already identify
Claude. These staged edits must be integrated after the frozen suite completes.

Limits: Windows only, one host, loopback transport, development packages,
Connector installed in this test environment (though the local path did not
use it). This does not establish the real-provider campaign in an environment
without Connector, independent-host acceptance, UI acceptance, Linux matrix,
all controls or final M13/G0–G3 completion. Remote CLI validation is separate.
