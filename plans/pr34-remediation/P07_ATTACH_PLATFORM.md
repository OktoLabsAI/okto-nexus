# P07 — attach platform boundary

Parent SHA: `ab7d56c`. Branch: `feature/v0.2.0`. This is a partial P07
checkpoint, not the final gate.

`ClaudeCodeAttachConnector` now rejects unsupported platforms before registry
reads, process probes or socket creation. Discovery and the internal PID probe
share the same guard. `probe()` returns `platform_unsupported` in category
`unsupported_platform`; start/send/discovery raise CONFIG_ERROR. The production
adapter registry preserves all four entries, declares attach's POSIX requirement,
and reports platform compatibility separately from protocol capabilities. A
compatible platform does not imply a verified native peer/version.

Reason: `os.kill(pid, 0)` is a POSIX liveness check but can terminate the target
on Windows; see [Python's os.kill contract](https://docs.python.org/3/library/os.html#os.kill).
AF_UNIX availability alone does not establish POSIX UID/ownership semantics.
No native attach session, credentials, socket, or process was used in this unit.

Behavioral reproduction before the fix:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_attach_platform.py -q --tb=short`

FAIL: unsupported attach attempted registry access, evidenced by
`evidence/p07-attach-platform-red.log`. The test traps effects rather than calling
a real PID probe, and can exercise this boundary on either host platform.

After correction:

`.venv/Scripts/python.exe -m pytest tests/test_runtime_attach_platform.py tests/test_claude_code_attach_connector.py tests/test_runtime_contracts.py -q --tb=short`

13 passed, 57 skipped; `evidence/p07-attach-platform.log`. The 57 POSIX attach
fixtures are **NOT_RUN on Windows**, not PASS or NOT_APPLICABLE. Portable skip
guards also remove the baseline os.geteuid collection failure.

`.venv/Scripts/python.exe -m pytest --collect-only -q`

2011 tests collected successfully; `evidence/p07-collection.log`. Collection is
not a full-suite execution. Ruff passed for the four changed Python files.

Changed symbols: `_require_attach_platform`, attach discovery/probe/start/send,
`build_connector_factories`, `capabilities_catalog`; tests in
`test_runtime_attach_platform.py` and POSIX guards in
`test_claude_code_attach_connector.py`. No schema change or migration.

Remaining: actual POSIX attach campaign requires a dedicated isolated session
and supported host; native result remains NOT_RUN. Managed Claude stream on
Windows remains available. Next P07 work: bounded protocol readers/buffers,
active-turn close, owned POSIX process cleanup and boot/recovery.
