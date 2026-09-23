# Owner-scoped opening and stale-session recovery

2026-09-23; parent 6b1358d plus this worktree; feature/v0.2.0.
Requirements: F04/F11, T-ID-06, T-DISP-05/06, T-LIFE-01 (partial).

Migration 038 extends runtime_open_requests instead of duplicating HarnessSession.
RESERVED is logical STARTING: durable endpoint/revision/profile/owner/deadline
before construction, environment resolution or native effects. Legacy requests
without a client key receive a generated key; returned request_id supports
diagnosis, but a client that lost its generated key cannot assume retry safety.
Both explicit opens and on-demand delivery construction reserve this binding.

Supervisor validates the reservation before native start and again before
publishing readiness, including current owner/lease, deadline and profile/endpoint
revision. Sessions persist owner_epoch. Failed late starts retain unknown request
outcomes and use the existing owned-resource teardown.

After journal recovery, previous-owner readiness becomes unknown/ERRORED, with
no invented native ended_at. Only that runtime canonical presence closes;
independent Agent sessions remain active. Affected endpoints and unfinished starts
are quarantined (owner_lost); requests become OUTCOME_UNKNOWN, never replayed.
Selection, access and immediate dispatch revalidation respect quarantine.
Historical session reads carry owner_epoch; stale rows cannot select a live lane.

Behavioral REDs: missing reservation at constructor entry and historical
protocol_ready surviving fresh composition takeover (2 failures, 3.18s).
Tests use production HTTP/composition and disposable state cuts; no native
SIGKILL claim from these state-restoration tests.

Commands, prefixed rtk proxy:
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_session_recovery.py tests/test_runtime_restart.py tests/test_runtime_outbox.py --tb=short
  21 PASS, 48.96s (initial two new cases).
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_session_recovery.py tests/test_runtime_restart.py tests/test_runtime_outbox.py tests/test_pr34_remediation.py tests/test_runtime_shutdown.py tests/test_runtime_shared_connection.py tests/test_runtime_grants.py tests/test_runtime_endpoints.py --tb=short --maxfail=8
  100 PASS, 1 FAIL (known expired legacy relay, pending P10), 1 teardown ERROR,
  170.01s. Teardown traced to legacy replay fixture appending directly to SQLite
  after ingress sequence initialization, causing a fixture-only close collision.
  Updated that fixture to capture through ingress and assert stable replay IDs.
- .venv/Scripts/python.exe -m pytest -q tests/test_runtime_session_recovery.py tests/test_pr34_remediation.py::test_replay_keeps_event_id_and_sequence --tb=short
  5 PASS, 7.83s (includes revoked binding before spawn and unfinished-start recovery).
- Ruff on changed Python files: PASS.

Native providers NOT_RUN for this unit. Failed broad command is not relabeled
PASS. Operator reconciliation and stable approved boot follow next; durable
control intents, publication, artifacts, P09-P12 remain pending. No gate promotion.
