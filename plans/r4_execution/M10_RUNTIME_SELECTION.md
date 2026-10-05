# R4 dashboard selection — 2026-10-02

The connection panel now reads executor choices and Core-produced runtime options.
It does not infer an adapter catalog or native readiness in TypeScript. Operators
select a host, installation and logical workspace explicitly. Selection retains
executor ID, adapter ID, candidate reference and inventory revision, never an
array index. Reload/focus/periodic reads invalidate stale or revoked choices and
discard responses from superseded requests. No selection starts or approves work.

`GET /v1/agents/{agent_id}/executors` supplies a bounded, paginated, path-free
directory. Authentication is revalidated in the read transaction. Operators can
inspect another Agent; ordinary Agents see embedded hosts, their registrations
and executors with their approved enabled R4 endpoints. Revoked executors are
excluded. Host control state is not promoted into runtime readiness.

The R4 client uses Bearer authentication and direct JSON. Legacy `/api/v1` keeps
its existing client/envelope. Development Vite now proxies `/v1`. The old profile,
endpoint and connection-key controls remain in a collapsed maintenance section,
with explicit warnings that they do not create R4 bindings.

## Verification

- TypeScript build passed. Wheel and sdist were built in an isolated source copy
  with freshly compiled dashboard assets; preexisting worktree assets were not
  overwritten. The build manifest records the shipped bytes.
- Eight source API checks passed: authentication/scope, pagination, revoked hosts,
  approved-bound subject visibility, redaction and invalid queries.
- Real Edge selection check passed. Two identical executable copies receive
  distinct Core references/labels. Selecting the second reference survives a
  deliberate response presentation reorder, then is cleared when freshness proof
  disappears and when the host is revoked. No R4 mutation is sent by this panel.
- Installed campaign passed 24 tests in 63.88 seconds: directory, runtime-options,
  packaged HTTP/OpenAPI and Edge selection. The browser served the wheel's actual
  HTML/JS/CSS. All three installed package trees matched their wheels and all
  monitored campaign inputs remained unchanged.
- Documentation audit passed seven actual CLI help commands, fifteen installed
  route declarations and five local links. Its output now describes scopes it
  does not verify, rather than incorrectly reporting historical TN-38/39/40
  evidence as missing.

See [installed campaign](evidence/runtime-selection/installed/campaign.json),
[artifacts](evidence/runtime-selection/build-manifest.json) and
[documentation audit](evidence/runtime-selection/docs.json).

Nexus wheel SHA-256:
`d4b359b3f02e1dcf1d2e150df373dcde58a03a384900e1561a7c006703173c50`.
Nexus sdist SHA-256:
`759af842071008834b7d4be74e126772f6f9e2f7408f6346f875fa99f239bf09`.
These are development artifacts, not the final M13 freeze.

## Scope and retained unsuccessful attempts

The browser routes requests through the production FastAPI TestClient; this is
not a real network or independent-host campaign. Inventory and connectivity are
synthetic fixture setup; native qualification is not overridden into a provider
acceptance claim. An infinite SSE stream cannot be buffered through TestClient:
the first browser attempt was explicitly terminated to correct that fixture.
SSE is now stubbed and is outside this test's scope. A later test assumption that
identical copies share a display label failed: Core correctly adds a distinct
reference suffix. That failed JUnit is retained; the test now asserts distinct
references and uses Core labels unchanged. The passed source and installed runs
follow those corrections. The fixture does not serve the general logo asset;
the selection screenshot is not a full-site visual acceptance.

NS13.01 remains partial: cross-OS peer API revision change, prepare/apply refusal,
and the normative end-to-end UI scenario still need coverage. Consent/realization
and binding apply, reusable binding selection, runtime operations/decisions,
operator delegation, embedded observation and active inventory refresh are still
needed. The panel says so and exposes no placeholder approval/start button.
NS15.05, M13 and G0–G3 remain open for their full scope.
