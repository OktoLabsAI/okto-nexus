# R7 validation progress

Candidate source: `01b0de385398950ac4547aa8a5dcbc29473c12cb`.
Wheel: `18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681`.
The package prefix is frozen; evidence-only commits do not change this candidate.

The complete selected source regression passed **321 tests**, with four warnings,
in 723.81 seconds. Its source/test guards report no drift; the owned process
exited normally with no timeout, force action, remaining known process or
listener. See `source-tests/r7-home/qualification.json` and the associated XML.
This run explicitly imports repository source using isolated dependencies and
does not qualify the installed wheel.

Build, wheel/sdist validation, isolated installation, pip check, package audit,
CLI smoke and actual HTTP/MCP smoke passed. The live smoke used two synthetic
identities and exposed 54 tools, with canonical stop and physical exit. There
were no provider calls. See `package-hst-r7/qualification.json`,
`package-hst-r7/live-qualification.json` and the frozen manifests. Neither a
package-ready marker nor a smoke test establishes feature qualification.

The fresh installed browser regression passed **21 checks**, with no failed
checks or browser POST. It covered Working with an independent request,
full blocking after the parallel session finished, exact request/result
sessions, incomplete Results and canonical logout. The installed payload's
1,031 files remained unchanged. The owner drained normally; its unanswered
request's bounded per-session close remained unconfirmed. See
`browser-hst/r7-functional-report.md` for that limitation and all resource
observations. Seen mutation was not exercised.

The separate installed regression passed **326 tests**, with no skip, failure,
error or not-run case. All 1,828 source/test pins, 1,031 installed payload files,
copied tests and copied helpers remained unchanged. Its owner exited normally
without timeout, force, signals or remaining observed processes. See
`package-hst-r7/installed-qualification.json` and the phase inventory. The five
additional cases cover original-recipient authorization and private operator
message/handoff sessions; this is not a claim that all ledger criteria pass.

The exclusive ten-cut performance matrix subsequently completed normally:
five of eight candidate cuts passed and three failed the original 500 ms p95
target; both baseline cuts failed separately. OPEN100 V2 narrowly met the
target, but mixed100 V2 remained above it. The separate three-GET diagnostic
confirmed the result-attention fast path was active. See
`performance-hst/persistent-r7-final/qualification.json`,
`performance-hst/profile-r7-final/qualification.json` and the open
`performance-hst/r7-correction-plan.md`. Useful DOM remains unmeasured at
this checkpoint. No target waiver, native adapter campaign, screen-reader
qualification or human acceptance is implied.

The previous R6 performance failures and the first R7 source/test
failures remain in their original evidence cuts. The default rollout flag
remains off. No schema migration or Core/Connector change is introduced;
rollback remains presentation-only through the existing flag, preserving
canonical runtime state and data.
