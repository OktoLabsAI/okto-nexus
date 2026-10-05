# TR4-14-01 crash/restart history without a provider binary

The normative test starts a disposable application process with the installed Nexus/Core packages, admits a canonical local start and waits for its actual durable receipt. The native port is synthetic. The process exits abruptly through os._exit, without closing its native session or releasing its stores. The parent removes the disposable provider executable and waits for the persisted legacy dispatcher lease to expire naturally.

A second process runs the production serve entry point with an isolated PATH and the same home directory. It opens the persisted Core journal and ledger without constructing a runtime, reads the receipt, claim page, session fence and owned-slot page, and retains the unreleased slot. A runtime-construction sentinel fails the test if recovery attempts a native opening.

Over real loopback HTTP, the test reads the original client intent, operation and session, replays the original admission IDs, and refuses a new start. The original receipt remains available, ownership and process state remain UNKNOWN, and control is unavailable. Operator shutdown terminates the restarted application normally. The probe only verifies historical recovery; it does not claim physical process containment after the original crash.

The first run attempted restart before the old 40-second dispatcher lease expired and correctly received startup refusal. Its failing XML is retained. The corrected test reads the actual expiry from the disposable store and waits without rewriting authority state. No production change or rebuilt wheel was needed.

## Scope

The installed runner compares the current source, wheel and installation bytes for all three packages against ns14-02-artifacts.json, then runs NS14, NS09 and capability recovery regression. Results, commands and hashes are in test_runs_20261001_ns14_01.json.

TR4-14-01 is qualified at restart_integration on Windows. NS14.01 remains partial: full paginated obligation recovery, every prerequisite task, remote topology and final platform/provider qualification are not established by this two-process case. Actual Pi/Codex/Claude evidence retains its original artifact scope. All release gates remain open.
