# Home R1 UI qualification

The operational Home reuses the existing canonical composer, inspection body, dialog guard and runtime controls. The classic Home is retained as the independent presentation fallback. No new session is selected implicitly for a continuation.

The final Node run records 28 unique tests: 16 Home UI/continuation tests, six classic Home regressions and six modal-change regressions. These tests render actual TSX through React SSR and exercise exact-scope fake clients and deferred responses. They do not establish real DOM behavior. Browser focus, keyboard, drawer, network revocation and narrow-viewport findings are recorded separately by the root browser qualification.

`qualification.json` pins the implementation and test sources, records the final build, and preserves its limitations. The client feature flag is off by default at this source cut; any later default selection must be recorded separately. No runtime/provider effects were used for this qualification.
