# Read-only viewer change-capture regression

BXP antecedent: actual Home exact session output Auto-scroll had no `[data-modal-passive]` ancestor. Toggling it and pressing Close opened `Discard unsaved changes?` despite no form edit. `before-cli.txt`, `before-ready.json`, and before screenshot preserve canonical GET-only reproduction against `index-BXpHvePH.js`. Before fixture/browser closed normally0 and PID57300/listener51714 absent.

Fix: only SessionExecutionPanel's read-only section gained `data-modal-passive`. The modal's change-capture logic and canonical forms were unchanged. Node focal11PASS (tool d4dc1d): actual SSR SessionExecutionPanel contains the passive Auto-scroll boundary, actual RuntimeOperations sibling has message textarea with no passive boundary, and existing captured-draft success/failure/race tests remain passing. SSR useLayoutEffect warnings remain; Node is not browser proof.

After root's build, a new own real browser/fixture loaded `index-BGONNtiX.js` with the same CSS `index-C-ZFb395.css`. Four browser checks PASS (raw tool cb0eba): exact original session selected, Auto-scroll has passive ancestor and Close closes with no Discard; editing canonical New request Message still opens Discard; Keep editing preserves exact unsent draft; explicit Discard closes, with only real GET requests and zero page exceptions. No action was submitted. Console errors were not separately collected by this narrow runner, so no zero-console claim.

Screenshots preserve viewer and genuine canonical composer discard state. Actual envelopes, session IDs and import-time source/static pins are in before/after READY and raw CLI outputs. Qualification adds the modified viewer source plus unchanged stream/modal and regression-test hashes. This is a focused presentation fix proof, not full Home, campaign, AT, provider or human-usability qualification.

Own session `ui11-viewer-guard-after` close exit0; fixture session6152 exit0, shared WSS/lifespan/factory CLOSED normally; browser PID53208 and listener50898 physically absent. No forced stop, personal browser, account/auth reads or provider/native invocation. Installed BXP campaign package, proposal/candidate, campaign pins and pr08 report were not modified.

Reproduce with `prepare.py`, existing pr04 `fixture.py --expected-bundle index-BGONNtiX.js` and own ready/stop paths, own named CLI browser, `materialize-after.py`, then CLI run-code generated after-probe.js. Close only own session, touch own stop file, verify absence. `manifest.json` hashes local evidence bytes.
