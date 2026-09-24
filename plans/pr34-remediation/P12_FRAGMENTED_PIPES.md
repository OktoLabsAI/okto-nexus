# Fragmented UTF-8 and pipe pressure acceptance

Parent395d070; production code unchanged. T-LIFE-11 qualification requires the final manifests below; T-LIFE-03 active-turn SIGTERM remains a separate pending gate.

`tests/test_runtime_fragmented_pipes.py` runs the production HTTP/MCP composition with owned synthetic Pi/RPC, Codex/app-server and Claude stream-json peers. Each peer splits the four bytes of a real UTF-8 emoji across separate OS writes, with small delays between continuation bytes. Other accented and CJK text is preserved exactly through two turns and durable results. This exercises the actual TextIO decoder and native transport, not StringIO alone.

The peer adds128KiB of legal JSON whitespace to each Unicode-bearing frame, keeping it below the unchanged262144-character framing bound, and concurrently writes2MiB of newline-free stderr. These writes exceed ordinary pipe buffering; the test requires both streams to drain, two correlated terminal results, bounded retained stderr and owned process termination after canonical close. It asserts actual byte counters and fragmentation counts from the disposable peer. It does not measure exact OS pipe occupancy, indefinite saturation or general host exhaustion. No native-provider account is used.

Existing event-buffer tests add bounded history, subscription byte/count quotas, capacity release, explicit replay gaps and production overflow -> uncertainty/process cleanup. Existing protocol-limit tests reject oversized unterminated stdout in all three managed transports and persist an attributable production fault without a fabricated completion. Attach remains in the existing event-history bound test; it has no native NDJSON stdout/stderr stream to fabricate.

## Preparation failures

1. Initial3 FAIL: the new test passed an unsupported timeout keyword to the existing wait helper. Corrected the invocation; no product defect claim.
2. Diagnostic2 PASS1 FAIL: the Pi synthetic executable reported the Python version, so the runtime correctly refused unqualified conversation. The fixture now supplies the existing owned version-probe injection reporting the tested Pi0.85.1 fixture contract; it does not bypass capability verification or run installed Pi.
3. Subsequent2 PASS1 FAIL: Pi emits both native turn_end and agent_end in the generic turn_completed family. The assertion incorrectly counted that family as the logical execution terminal. It now checks the server's correlated delivery_phase=terminal, preserving both native facts and requiring exactly two durable logical results.

The prior failed process handle77008 was explicitly polled to terminal exit1; subsequent final handles were independently observed to exit0. No failed attempt is counted as PASS.

## Commands

```text
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_fragmented_pipes.py -q --junitxml=.git/pr34-evidence/fragmented-pipes-initial.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_fragmented_pipes.py -q --junitxml=.git/pr34-evidence/fragmented-pipes-diagnostic.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_fragmented_pipes.py -q --junitxml=.git/pr34-evidence/fragmented-pipes-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_fragmented_pipes.py tests/test_runtime_event_buffers.py -q --junitxml=.git/pr34-evidence/fragmented-pipes-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_fragmented_pipes.py tests/test_runtime_event_buffers.py -q --junitxml=.git/pr34-evidence/fragmented-pipes-final-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_protocol_limits.py -q --junitxml=.git/pr34-evidence/protocol-limits-current-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_protocol_limits.py -q --junitxml=.git/pr34-evidence/protocol-limits-current-linux.xml
rtk proxy ruff check tests/test_runtime_fragmented_pipes.py
```

Final combined gate: Windows2563 has19 PASS26.25s; Linux1826 has19 PASS27.32s. Windows protocol-limit gate has5 PASS6.23s. Linux protocol-limit gate90609 has5 PASS11.16s, terminal exit0. These counts are fresh fixture runs, not old PR/native campaign totals. No phase/final gate promotion.

All final handles are terminal. Ruff and git diff --check PASS. The [acceptance index](evidence/p12-fragmented-pipes-index.json) verifies all required base names against passing parameterized nodes on both platforms and records24 distinct nodes/platform with exact source/test hashes. T-LIFE-11 scoped PASS; T-LIFE-03 remains NOT_RUN until the active-turn/journal signal stimulus is executed.
