# Audience and native authority acceptance

2026-09-24, feature/v0.2.0, parentfe2801e9afa333cf2405ca46a9e1b7e45fe0cfde plus test hashes. Production unchanged.

T-AUTH-03: new test_runtime_read_audience.py first generates a nonempty private durable result and replay using the actual production Codex transport with an owned Python fixture. The operator can read it. A foreign authenticated actor cannot read the session, replay or result, nor enumerate profiles/endpoints/diagnostics over REST or MCP. Known and missing session replay/get denial envelopes are identical; private markers and paths are absent. Safe discovery returns the same empty projection on both surfaces. Existing discovery tests cover narrow authorized redacted projections and revocation.

T-AUTH-07: extend the real-pipe structured work result mutation matrix with actor_agent_id, from_agent_id, execution_grant_id and root_operation_id. Existing operation/handoff/epoch/action/agent mutations remain. Each forged result leaves the handoff CLAIMED with no applied result and a durable BLOCKED outcome. Combined with the existing control payload boundary test, both request and native result authority inputs are exercised. No protocol metadata is treated as authentication.

T-AUTH-06: new test_runtime_revocation_during_turn.py controls a real synthetic native turn with a temporary file release. It observes HARNESS_ACCEPTED with no terminal/result, positively reads under the grant, revokes that grant through REST, and proves subsequent send/read denial. Only then does the peer emit its structured terminal. Original acceptance and private evidence remain durable, one operation/result exists, and completion/publication are blocked while the handoff remains CLAIMED. The peer's wait has a deadline and teardown owns the process. No provider, ambient account or personal session used.

Initial Windows79145:11 PASS42.51s for audience/forged native authority. Initial during-turn case:1 PASS4.84s. Ruff PASS. No product defect or source change in this unit.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/audience-fe2801e-windows.xml tests/test_runtime_read_audience.py tests/test_runtime_revocation_during_turn.py tests/test_runtime_work_results.py tests/test_runtime_payload_boundaries.py tests/test_runtime_discovery.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/audience-fe2801e-linux.xml tests/test_runtime_read_audience.py tests/test_runtime_revocation_during_turn.py tests/test_runtime_work_results.py tests/test_runtime_payload_boundaries.py tests/test_runtime_discovery.py
rtk proxy ruff check tests/test_runtime_read_audience.py tests/test_runtime_revocation_during_turn.py tests/test_runtime_work_results.py
```

Terminal expanded outcomes, test hashes and per-node manifests follow. This scoped qualification does not close lifecycle pressure, full matrix, comparative performance or release gates. Independent new replay tests were developed without changing any production/source files used by these running selections.

Expanded Windows84763:36 PASS140.34s/Linux76723:36 PASS168.22s, both exit0. Persistent XMLs reduced and each mapped node/parameter required PASS on both. No live processes from this unit. T-AUTH-03/06/07 scoped PASS; hashed manifests qualify the parent plus test edits.
