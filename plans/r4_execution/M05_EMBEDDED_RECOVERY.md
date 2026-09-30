# M05 — Embedded historical receipt recovery

Status: partial recovery implementation. M05 and G1 remain open.

Serve startup scans pending local publication records in pages of 128 before considering new dispatch. For each record, the host opens the retained per-session Core journal, reads the durable receipt through Core's public journal API and closes the journal. It does not compose a runtime, resolve provider credentials, validate the executable, acquire the slot ledger or launch native work. Missing journals stop recovery and do not create replacement files.

The current embedded owner authorizes persistence inside the receipt transaction. The persisted Core receipt binding validates the historical source, while the canonical dispatch and applied lease validate its original authorization. The receipt retains its original connection ID and generation. Existing session projection rules prevent historical receipts from making the successor executor or session ready. The terminal publication flag is completed after receipt acceptance.

History producers remain retained if their observers are canceled. Host shutdown joins them so an open journal cannot be abandoned. Existing runtime-owned journal reads remain unchanged.

## Verification

The restart scenario uses real serve startup, public preparation/binding/grant/admission and a technical native factory. A storage trigger rejects the close receipt after Core has stopped the native session. After shutdown, the trigger and synthetic provider executable are removed. The successor owner recovers the terminal receipt with its historical source and no native reopening. A second case removes the journal and verifies that recovery stays pending without manufacturing a new journal or successful receipt. A directed cancellation test holds a history read, cancels its observer and verifies that host shutdown waits for journal closure.

Final installed results: 89 passed in the normal environment and 50 overlapping tests passed in the actual no-Connector environment, with pip check. The source regression covered 14 tests before the additional cancellation case. Installed results and artifact hashes are recorded in test_runs_20260930_embedded_recovery.json. The installed runner verifies source, wheel and installed package bytes and uses an external working directory with isolated Python imports. The no-Connector environment verifies module and distribution absence. Its cases overlap the normal environment and are not additive coverage.

## Remaining fixed-plan work

Retained stores still require resource/slot reconciliation and event replay before CONTROL_READY. This increment does not adopt native sessions, release unknown resources, infer missing receipts or replay operations. Recovery errors remain observable on the serve-owned dispatcher and keep it inactive. Complete recovery, event integration, tools/vault, approvals/input, production contract qualification and real Pi/Codex/Claude journeys remain required by the delivery plan.

Core and Connector artifacts are unchanged. The Nexus wheel includes preexisting user UI edits; those assets are excluded from this commit and UI acceptance. The existing Starlette/httpx dependency deprecation warning remains.
