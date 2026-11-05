# R3 baseline and implementation map — 2026-11-05

Scope: the unchanged root R3 plan (59 tasks / 132 scenarios / 28 invariants /
17 completion criteria). This inventory is evidence of current paths and gaps,
not acceptance of M1 or new platform qualification.

## Repositories and instructions

| Repository | Fetched main used as base | Base version | Working branch / candidate |
|---|---|---|---|
| Nexus | `c1e78e26fb2bd57ace3370417a2cb7529856b603` | 0.3.2 | `feature/v0.3.3` / 0.3.3 |
| Core | `19c99f15b17ae994653ad9e190964229a0e296e8` | 0.0.13 | `feature/v0.0.14` / 0.0.14 |
| Connector | `a3017d97b6a295cb2b46b9dd391b4c04ed121ee2` | 0.0.11 | `feature/v0.0.12` / 0.0.12 |

The original working HEADs were Nexus `d881266`, Core `2182b36`, Connector
`1d1ee73`. Tracked files were clean; the user-provided R3 plan was untracked and
preserved. Before switching, HEAD was respectively 91, 15 and 5 commits behind
fetched main, with no commits unique to the working branch. No reset or merge of
old branches was performed. The new branches start directly at fetched main,
as requested by the user. Preparation commits pushed: Nexus `ff6ee26`, Core
`2093863`, Connector `7fd37c8`.

User instructions load `C:/Users/jpamb/.codex/RTK.md`: prefix shell commands with
`rtk` (use `rtk proxy` for unfiltered/custom commands). No repository AGENTS.md
was found in the three tracked trees. User explicitly requires a root ledger,
fixed plan scope, versioned branches, and commit/push at each milestone. This
does not authorize publishing packages or using provider credentials. Local
`CLAUDE.md` contains historical CLI/auth/CI claims; actual code and tests win.

The plan's snapshots are older than these bases. Main already includes durable
runtime recovery, process ownership, handoff capacity/dispatch, discovery and
configuration improvements. These mechanisms are reused, not reimplemented.
The Core R4 wire revision is unchanged by candidate version bumps. Both hosts
pin Core 0.0.14; its vendored wheel is byte-identical in both repositories.
Nexus `uv.lock`, frontend package metadata, and CI artifact manifest are aligned.

Compared with the plan's original SHAs, fetched main changes 151 Nexus files
(8,237 insertions / 1,381 deletions), 19 Core files (475 / 24), and 5 Connector
files (16 / 10), as reported by `git diff --shortstat ORIGINAL_SHA MAIN_SHA`.

## Canonical paths and transaction boundaries (BASE-02)

| Path | Existing implementation | Boundary / reuse / gap |
|---|---|---|
| Native request → decision | `application/execution_native_requests.py:project_native_request`; `execution_native_decisions.py:ExecutionNativeDecisions`; `/v1/runtime/input-requests`, `/v1/runtime/approval-decisions` and decision GET in `runtime_v1.py`; same routes adapted by `dashboard_runtime.py` | Request is projected from a canonical runtime event. Decision validates actor, request hash, exact key/revision, expiry and live operation; domain approval commits correlated decision/operation. Dispatch revalidates. CLI must reuse this, never send a prompt as approval. |
| Broadcast handoff → MCP/runtime claim | `application/handoff.py:handoff_claim`, `claim_managed_in_transaction`, `_claim_in_transaction`; `handoff_runtime_scheduler.py` and canonical claim repos | Both converge on the same conditional claim under the SQLite write UoW, preserving claim epoch. Managed admission/capacity are additional gates, not an alternative claim owner. Existing commit-cut tests cover rollback. |
| Message → inbox/outbox | `application/messages.py:MessageService.create_message`, `_send_uow`, runtime delivery preparation and inbox delivery; domain event before commit | Message, recipient inbox, runtime intents and event commit together. Subscriber wake/notification is a post-commit hint. Guardrail/governance denials roll back and audit separately. No public generic client request ID exists in this signature. |
| Handoff creation | `HandoffService.handoff_create`, `_create_uow`, canonical repo and notifications | Same transaction includes handoff, notifications/events and admission side effects. No generic creation request receipt: DX-10 remains required. Existing native operation receipts do not deduplicate this call. |
| Setup → temporary test → Finish | `runtime_v1.py` setup routes; `application/connection_test.py`; `application/connection_setup.py:load_setup, finish_setup, SetupTransaction` | Next only validates browser draft. Finish wraps policies, realization, binding, preferences, grant and `connection_setup_commits` in one UoW; actor + client intent + semantic digest and revisions fence replay/concurrency. Host/vault effects are not in this DB transaction. Current local Finish requires successful temporary model test; DX-15…20 must reconcile this with optional paid smoke and reviewed nonproductive connection. |
| Renderer → client file | Core `harness_config.py`, `config_document.py`, `config_persistence.py`; Connector `services/mcp_config_service.py:plan_direct_entry, apply_persistent_entry` | Existing managed HTTP template requires `mcp-cap:` and qualified format. JSON/TOML planning and atomic backup/CAS primitives can be reused, but do not accept canonical participant keys as capabilities. Existing Connector plan/apply recomputes a plan on apply; participant reviewed-plan CAS needs its own preserved revision. |

SQLite implementation: `adapters/outbound/sqlite/connection.py:SqliteUnitOfWork`
uses `BEGIN IMMEDIATE` for writes, deferred `BEGIN` for reads, commits on clean
exit, rolls back on exception and releases its connection/writer gate. No new
network wait may hold this transaction. Setup's transaction facade reuses the
same UoW for nested canonical services.

## Lifecycle, state and existing terminal surfaces (BASE-06)

### Server

- Foreground: `adapters/inbound/cli/main.py` → `serve.py:run_serve` →
  `RuntimeServer` / `http/app.py:lifespan`. CLI currently exposes serve, tail,
  admin, provider-credentials; there is no high-level connect/service command.
- Configuration: `config.py:load_config`, CLI/env/default precedence; home and
  `nexus.db` can be independently overridden. `serve` defaults to `0.0.0.0:8202`,
  not loopback. Preserve explicitly selected bind/origin/TLS settings.
- Existing `ServeLock` is an exclusive-create JSON/mtime file per home. It
  permits stale-heartbeat takeover even without proving the owner is dead and
  bootstrap/migrations currently happen before lock acquisition. Different
  homes can select one DB. SVC-02 must fix these gaps before start/reuse is safe.
- `/healthz` is public liveness, not instance-specific readiness. `/api/v1/info`
  is also public. New readiness must correlate the configured instance, active
  package, generation and initialization, not accept any reachable port.
- `bootstrap/server_runtime.py`, `server_shutdown.py`, `embedded_supervisor.py`,
  runtime admission fence and dispatch recovery already exist. Shutdown fences
  new work, retains stores/transport until owned resources drain, and flips
  `server.should_exit` only on completion. Reuse `/v1/runtime/shutdown` and the
  coordinator. Its dashboard facade currently omits shutdown; local operator
  CLI access needs the existing auth path, not a new admin secret in a harness.
- Process owners are Core Windows Jobs / POSIX guardians and canonical journals;
  no PID scanner or task replay is justified by daemon availability.

### Connector

- `cli/main.py` dispatches existing connect, configure, status, doctor, runtime,
  daemon and service commands. `daemon/manager.py:start` starts detached Python
  with stdio detached, Windows Job breakaway or POSIX new session. `daemon run`
  is foreground. IPC ping proves local health; WSS/auth/admission are separate.
- `daemon/lock.py:InstanceLock` uses a held OS lock and readiness with PID/birth
  evidence plus authenticated IPC. Reuse it. Contended acquire currently returns
  before closing the failed descriptor; include this existing gap in SVC-11.
- Persistent root: `platform/paths.py`; identity/vault: `identity/`; runtime and
  request data: `storage/`; discovery and launch references: corresponding
  `services/` modules. No new credential store or executor identity is needed.
- `platform/service_install.py` has systemd-user, launchd-user, schtasks-logon
  integration. It uses one global service name, overwrites definitions, has
  unqualified survival booleans and incomplete quoting/recovery semantics.
  `daemon start` does not route through an installed supervisor. SVC-05/11 must
  add instance scope, revision/ownership checks and supervisor-aware control.
- Runtime start/submit/operation/inspect already preserve explicit client intent
  IDs. Runtime logs is documented as a legacy surface, not complete R4 history.
  Canonical native question/permission handling and operator terminal workflow
  remain missing. `--operator-identity` is not a reason to copy operator secrets
  to the execution host.

### Core and packaging

Core imports no application and owns native discovery, adapter registry,
configuration validation, process containment, journals, contracts and packaged
schemas. `discover_installations`, catalog/availability and configuration probes
already separate detection from qualification. Reuse those functions. Do not
give Core identities, HTTP product routes, inboxes or a service scheduler.

Core/Connector use setuptools and package resources; Nexus also ships built
frontend and SQL migrations. Existing `tools/ci_installed.py` validates vendored
artifact hashes, installs a wheel and tests outside the checkout. Connector
`tests/e2e/test_packaging.py` performs a clean venv install. CI tests Windows and
Linux; this does not prove login/logout or providers on either platform.

## First-use baseline and platform decision

Initial campaign target: Windows 11 build 26300, Python 3.13.1, both local Server
and Connector on isolated roots. First intended harness: `codex_app_server`,
which has existing native decision support and historical Windows campaigns.
Current executable qualification must be freshly checked; PATH contains Codex,
Claude and Pi launchers, but this is not authentication or version qualification.
Herdr was not found on PATH. Do not infer its absence on every possible host.

Baseline UI has seven setup stages (Host/harness, Installation, Folders/login,
Connection, Preferences, Authorization, Test) followed by Finish. Server-local
first use requires manual foreground service and dashboard. Connector can start
its daemon and conduct its existing wizard, but normal decisions/results are not
a complete dashboard-free terminal cycle. Time to first useful provider result
is **NOT_RUN**, because no real provider campaign was authorized. The disposable
foreground timing in `evidence/baseline-startup.json` only measures HTTP liveness;
it is not substituted for that missing measurement.

| Platform | Existing mechanism | R3 qualification now |
|---|---|---|
| Windows | Connector detached + logon scheduled task; Server foreground | Unit/integration and isolated package evidence only; service/login/logout/crash/terminal-survival campaign pending |
| Linux | Connector detached + systemd user; Core process guardians | Not executed in this R3 run; linger remains separate and opt-in |
| macOS | Connector detached + LaunchAgent; Core native ownership | Not executed in this R3 run; GUI login requirements and historical limitations preserved |

## Tests, baseline failures and documentation (BASE-03)

All shell commands below use the RTK prefix. Preparation: 34 passing tests in
`evidence/preparation-*.xml`. Wider baseline path suite is recorded separately
in `evidence/baseline-paths.xml`. Frontend uses `node --test tests/*.test.mjs`
(36 tests). PR-00 exposes this same runner as `npm test` and adds it to CI.
`npm run build` builds TypeScript and Vite;
the existing large-bundle warning is not a functional failure.

The first wider run exposed an incomplete bump: the runtime's
`CORE_INVENTORY_VERSION` still required 0.0.13. This is a preparation regression,
not a preexisting product failure. It was corrected to 0.0.14 before repeating
the affected tests; earlier failing results are not counted as passing evidence.

Repeated path suite: 64 passed. Inventory/pin suite: 8 passed. Existing Core
configuration/persistence tests: 51 passed; Connector managed MCP configuration:
7 passed. Frontend: 36 passed and production build succeeded. Runtime native
peers in these suites are test doubles, not paid providers. The disposable
foreground measurement reached HTTP liveness in 7.811 seconds and completed
canonical shutdown with `DRAINED`; a synthetic operator key was created only
inside that temporary home, retained in memory and never printed. The initial
measurement's immediate filesystem cleanup raced a Windows handle after child
termination; the successful measurement uses canonical shutdown and awaits exit.

Corrected the onboarding placeholder from a hardcoded HTTP URL with query key
to the current origin and Bearer-header guidance. Clarified that managed
MCP-only selection disables runtime, whereas adding an external participant
must preserve it. `automatic_reply` remains normalized compatibility data;
Next does not persist and Finish does. Existing generated snippets that expose
keys in argv/export text remain a named DX-04 gap; no broad secret-safety claim
is made for BASE-03.

Next dependencies: PR-01 implements SVC-01…04. PR-02 extends/reuses supervisors
and Connector. PR-03 supplies the preset and complete terminal cycle. Full
provider, real service-manager and later Herdr campaign gates stay open until
executed with the required authorization and environment.
