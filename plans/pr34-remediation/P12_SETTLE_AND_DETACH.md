# P12 — observed Pi settle and external attach preservation

Parent `4915878a0a66d9cf384ff719455e61175a5d9bfa` plus exact test hashes in `evidence/p12-settle-detach-index.json`. Production unchanged; feature/v0.2.0.

T-LIFE-09: real owned synthetic Pi RPC process emits its abort settle event. A deterministic barrier holds that actual frame before the connector observes it; the original interrupt thread is still waiting for the protocol reply. Reprompt, steer and a second interrupt all fail CONFLICT during the barrier. Releasing the frame permits interrupt to return; a new turn then reaches agent_settled. No fixed sleep selects the protected interval, no fabricated native ACK/order/capability. Existing next-turn-boundary steering and post-settle reprompt cases also run. This is protocol-fixture qualification; native Pi remains NOT_RUN.

T-LIFE-06 (POSIX fixture): real Unix socket/registry/token fixture through authenticated HTTP/MCP opens and receives ackless input as SENT_UNCONFIRMED, never result_durable. Unsupported controls fail; durable close reports detached with no close frame sent to the external peer. The external test process still exists and a fresh connector can probe/send another message to the same listener afterward. Attach sockets close per call and the adapter owns no persistent process/socket to terminate. Windows rows remain POSIX skips; this does not qualify a dedicated native Claude interactive session.

## Commands and observed outcomes

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pi_settle_acceptance.py tests/test_runtime_attach_compatibility.py tests/test_harness_pi_connector.py::test_steer_is_queued_immediately_and_delivered_at_turn_boundary tests/test_harness_pi_connector.py::test_interrupt_blocks_further_sends_until_agent_settled -q --junitxml=.git/pr34-evidence/settle-detach-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pi_settle_acceptance.py tests/test_runtime_attach_compatibility.py tests/test_harness_pi_connector.py::test_steer_is_queued_immediately_and_delivered_at_turn_boundary tests/test_harness_pi_connector.py::test_interrupt_blocks_further_sends_until_agent_settled -q --junitxml=.git/pr34-evidence/settle-detach-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pi_settle_acceptance.py tests/test_runtime_attach_compatibility.py tests/test_harness_pi_connector.py::test_steer_is_queued_immediately_and_delivered_at_turn_boundary tests/test_harness_pi_connector.py::test_interrupt_blocks_further_sends_until_agent_settled -q --junitxml=.git/pr34-evidence/settle-detach-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pi_settle_acceptance.py tests/test_runtime_attach_compatibility.py tests/test_harness_pi_connector.py::test_steer_is_queued_immediately_and_delivered_at_turn_boundary tests/test_harness_pi_connector.py::test_interrupt_blocks_further_sends_until_agent_settled -q --junitxml=.git/pr34-evidence/settle-detach-final-linux.xml
rtk proxy ruff check tests/test_runtime_pi_settle_acceptance.py tests/test_runtime_attach_compatibility.py
rtk git diff --check
```

Preparation Windows10761: **2 PASS9 SKIP1 ERROR5.46s**, missing two imported fixture dependencies in the new Pi test. Linux29154: **10 PASS1 FAIL1 ERROR39.85s**, same fixture error plus test cleanup called nonexistent attach.close after its preservation assertions had passed. Imported the dependencies and removed that unsupported cleanup call: the actual attach adapter has per-call sockets and no close method. These are test preparation failures, not reproduced production defects; retained manifests distinguish ERROR/FAIL from PASS.

Final Windows51284 **3 PASS9 SKIP9.12s**, Linux97257 **12 PASS31.20s**, terminal exit0. Ruff/diff PASS. No production change, new migration, live MCP smoke requirement or installed provider campaign. Raw XML remains under .git/pr34-evidence; sanitized node results in index.

Next: remaining16 original rows, final immutable-source suites and finding/operations/release audit/build/reinstall0.2.0. Gates requiring native Pi or dedicated attach still do not pass. Final gate NOT PASSED.
