# Diagnostic heartbeat isolation

The serve lifespan previously read the diagnostic lock payload and touched its
mtime synchronously on the HTTP event loop. `heartbeat_async` now performs that
filesystem operation in a worker. Each iteration awaits completion, so slow
storage cannot accumulate concurrent heartbeat jobs. Cancellation joins the
in-flight worker before normal lifespan cleanup releases the OS ownership locks;
repeated caller cancellation cannot abandon that worker.

This removes a concrete event-loop blocking path. It does not establish that the
heartbeat caused all observed v14 HTTP timeouts. Live read-only observations also
found host CPU saturation and main-thread samples waiting in Windows IOCP. The
active campaign installation remains unchanged, with zero new v14 model calls.
The GET identity revision writer was reviewed separately; removing its writes
would change revision semantics and is not part of this fix.

Validation on 2026-11-14:

- `tests/test_serve_lock_async.py tests/test_serve_lock.py`: 16 passed in 13.61s.
- `tests/test_server_effective_policy_http.py`: 14 passed in 125.33s, with the
  existing Starlette/httpx deprecation warning.
- Ruff on app.py, lock.py and the new test: passed. The first attempt using
  `.venv/python -m ruff` found no Ruff module; the installed Ruff executable
  completed successfully.
- Independent source review found no blocking issue in normal lifespan shutdown.

The regression test blocks the heartbeat worker, demonstrates that the event
loop still runs, issues two cancellations, and verifies ownership stays held
until the worker finishes. A second test preserves a changed generation. The
existing lifespan suite exercises real app startup/shutdown and lock authority.

Limit: waiting for completion is not filesystem I/O preemption. Hung filesystem
I/O can still keep shutdown pending while ownership is retained. No installed
wheel or real-campaign acceptance is claimed by these source tests. Existing
scenario and acceptance statuses remain unchanged.
