# Current dashboard qualification on the corrected candidate

Base39c5e6cc44481467a6785b09e11219f5c57b2f62 plus the four detached correction
hashes in [the manifest](evidence/p12-regression-dashboard.json). Windows execution
15582 completed exit0:15 PASS378.73s. No source/test changes occurred during it.
The concurrent full suites use unchanged main implementation; timings are not a
benchmark. Main integration and final regression remain pending.

The actual Edge browser used fresh temporary profiles, chromium_sandbox=True,
and context network restrictions to the disposable fixture loopback service.
Only temporary-built frontend assets were intercepted. API authentication,
permissions, lifecycle, native approval/input and outbox state came from the real
production composition with synthetic protocol processes. No provider/model,
operator account or personal browser profile was used. Repository static changes
were preserved. npm ci and temporary Vite builds passed.

Coverage includes explicit answers and primitive form types, no default answer,
Claude multi-choice, rejection without fabricated input, permission/input
separation, expiry, qualified capability restrictions, unknown transport,
detached external runtime, ambiguous binding, credential downgrade clearing prior
operator data, admission-OFF inspection and native approval navigation. Exact
nodes and outcomes are in the generated manifest; Linux browser remains NOT_RUN.

Reviewed screenshots:

- [Native answer form](evidence/p12-regression-dashboard-input.png): explicit
  green/3/No values and explicit empty text; the original request remains visible.
- [Runtime diagnostics](evidence/p12-regression-dashboard-diagnostics.png): one
  canonical identity with endpoints, detached lifecycle, separate command versus
  delivery, OUTCOME_UNKNOWN, transport-write evidence and exact recovery metadata.
  No automatic retry button or false completion is shown.

A fresh headless/sandboxed version-only probe immediately afterward observed
Edge153.0.4234.48, Python3.13.1/Windows11 AMD64, Playwright1.63.0 and httpx0.28.1.
It opened no page or personal profile. Raw XML/output stays private; committed
screenshots contain only disposable fixture data. Source hashes and exact child
argv/environment are retained in the manifest.
