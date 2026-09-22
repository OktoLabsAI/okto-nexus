# P07 — bounded native framing

Parent SHA `fdfc994`; branch `feature/v0.2.0`. Partial implementation of
T-LIFE-11. Final gate remains NOT PASSED.

All three managed adapters now share `framing.protocol_lines`: a bounded
TextIO read rejects a protocol line exceeding 262144 Unicode characters before
JSON decoding, including a line without a newline. This bounds the line's
character storage (at most four bytes per Python Unicode character), rather
than reading an unlimited line and measuring it afterward. A rejected frame
terminates the owned process and emits a diagnostic without its raw contents;
it never becomes a turn-completed event or a retry authorization. A shared
Codex process suffering a protocol fault loses that entire connection, not
just one thread. Native stop/outcome reconciliation remains a separate concern.

stderr uses 4096-character chunks and the adapters' existing bounded tail
counts. A long stderr line is drained in pieces; chunk boundaries are not
claimed as native line boundaries. Native event histories/subscriber queues
are still a separate unresolved memory bound; this change does not claim all
buffers are bounded. Input/output write deadlines are also separate.

Changed symbols: `protocol_lines`, `stderr_chunks`, `FrameLimitExceeded`;
Codex/Pi stdout/stderr readers; Claude stream stdout/stderr pumps.
No shared domain contract or migration changed.

Reproduction (actual temporary Python processes, no models):

`.venv/Scripts/python.exe -m pytest tests/test_runtime_protocol_limits.py -q --tb=short`

Before: 3 FAIL because each reader waited for newline/EOF instead of rejecting
an oversized unterminated frame (`evidence/p07-protocol-limits-red.log`). The
first run's fixture environment marker was corrected to `_NEXUS_PROFILE_ENV_SEALED`
before subsequent runs; the fixture executed only its temporary Python source.
After: 3 PASS (`evidence/p07-protocol-limits.log`). Expanded: 5 PASS
(`evidence/p07-protocol-limits-expanded.log`), including Unicode boundary and
stderr chunk checks and the actual REST/supervisor/native-transport/journal
composition. The production test observed a durable attributed fault with
event identity/sequence and no fabricated completion; it uses a scripted peer,
not a live provider. Every temporary owned process is reaped.

Regression command, with `OKTO_NEXUS_CLAUDE_LIVE=0`, `OKTO_NEXUS_CODEX_LIVE=0`,
`OKTO_NEXUS_NATIVE_CAMPAIGN=''`:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_protocol_limits.py tests/test_harness_codex_connector.py tests/test_harness_pi_connector.py tests/test_harness_claude_code_connector.py tests/test_runtime_shared_connection.py tests/test_runtime_process_ownership.py -q --tb=short`

104 PASS, 9 skipped, 1 warning in 101.79s. Evidence:
`evidence/p07-protocol-limits-gate.log`. The warning is the existing Pi fixture
which intentionally raises in the child-death callback; it is disclosed, not
treated as native success. Ruff passed for the five changed/new Python files.

Next dependencies: bounded native event retention and subscribers with explicit
overflow/replay behavior; active-turn shutdown; POSIX ownership and boot
recovery. Full T-LIFE-11 remains NOT_RUN as an aggregate until its remaining
pressure/buffer cases execute. Native Pi and attach remain NOT_RUN; earlier
real Codex/Claude two-turn evidence does not certify these later changes.
