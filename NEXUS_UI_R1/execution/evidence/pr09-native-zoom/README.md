# Native Chromium zoom200 focal

2026-11-16. Five browser checks PASS against `index-BXpHvePH.js` SHA256 `6872da3cff0444e43226a5aafdcb061f320f217e2eb6ceb83f80266e29a4d6c7`. Real GET-only canonical disposable fixture, no provider/native harness execution, personal browser or account. The isolated fixture uses the existing synthetic admitted WSS test peer.

Primary documentation was checked before launch: [Chrome tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs), [Playwright extension persistent-context requirements](https://playwright.dev/docs/chrome-extensions), and [Playwright CLI configuration](https://github.com/microsoft/playwright-cli/blob/main/README.md). Chrome documents `setZoom`/`getZoom`; Playwright documents bundled Chromium with persistent own profile and unpacked extension, including headless support. This uses the installed bundled Chromium executable, not personal Google Chrome.

The own MV3 extension has only loopback host permission and no content script. Its service worker calls `chrome.tabs.setZoomSettings` for per-tab scope, then `chrome.tabs.setZoom(tabId,2)` and `getZoom`. API result is2. With unchanged outer1440x1100, inner1424x1005 became712x502 and DPR1 became2. No CSS zoom, device-scale flag or emulated viewport was used.

Real Home loads and exact original session is selected in one Activity detail panel. Document scrollWidth/clientWidth are712/712; panel x35.60,width676.40 fits712 CSS pixels, Close element hit-tests and closes. All observed requests GET; zero POST/page errors/console errors. No full scenario or AT qualification is implied.

Screenshot limitation: Playwright's screenshot path captured only712x503 physical pixels at this native zoom, both with fullPage and viewport mode. Screenshots visibly crop the physical view; keep them as limited captures, not evidence that all visual content fits. The API/DOM geometry and successful actual selector/Close interactions independently prove the five named checks. No product defect is inferred from capture cropping. First run proved the same API/layout results; second run changed screenshot mode only and retained this limitation.

Reproduction: run `prepare.py`; launch named own CLI session with the generated `config.json`; launch existing `pr04-browser/fixture.py` with own ready/stop files and `--expected-bundle index-BXpHvePH.js`; run `materialize.py`, then CLI `run-code --filename` generated probe. Close only own named session and touch own stop file. Both finite runs exited0; own browser PIDs47660/42212 and loopback listeners58588/53859 were absent afterward. Fixture printed shared WSS/lifespan/factory closed normally. Neither user profiles nor sibling browsers were closed.

`ready.json` pins product/backend/static/fixture source at import. `browser-cli.txt` preserves second raw CLI result and executed script, `qualification.json` records exact checks/limits/cleanup, and `manifest.json` hashes local artifacts.
