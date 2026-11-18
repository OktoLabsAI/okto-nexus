# Native dialog focus diagnostic — prepared only

No Nexus or question is started. A finite stdlib loopback server serves only a static own HTML page in a fresh own Chrome CLI profile, with the same eleven sequential synthetic controls as the observed execution viewer. No authenticated state, fixture grant, producer, personal browser profile, AT installation, account, clipboard or external network resource is involved.

The controls are Expand/Close, Live tail/History, Pause tail, Auto-scroll, Latest events, three font controls and a focusable event list. They have no productive handlers; only Open calls native showModal and Close calls close. No custom Tab handler or focus trap exists.

Use actual Tab/Enter to open, record initial focus, then sixteen Tab and sixteen Shift+Tab observations. At every step record DOM focus count, Playwright focus locator count, document.hasFocus, active element tag/id/:focus, focus-visible/styles, UA :modal, and captured document/window focus/blur events. Observe rather than fail merely because document focus is absent. Fail if a genuinely focused page control outside the open modal is reached. Require all eleven controls including initial focus to be observed. Escape and return are benign and separately recorded.

Browser-only180s supervisor and90s finite HTTP server, own birth/executable/ancestry and manifest checks, normal browser/server stop first; owned-only containment is diagnostic failure. A single first-failure run requires a new root gate. No fallback, rerun or Nexus phase follows.

References checked read-only on 2026-11-17:

- [W3C H102](https://www.w3.org/WAI/WCAG22/Techniques/html/H102): a sufficient technique describes native dialog focus as limited to dialog contents and browser chrome. WCAG techniques are informative examples, not mandatory implementations.
- [Chrome accessibility guide](https://developer.chrome.com/docs/modern-web-guidance/guides/accessibility/accessibility#native-dialog): native showModal makes outside page content inert; browser chrome remains reachable; avoid adding a manual native-dialog trap.

These references motivate the diagnostic oracle; they do not prove the cause of the original I01 run. That cut remains partial. A future Nexus counterpart must separately observe its actual focused page element, initial focus and exact modal inventory before promoting I01.
