# C10 — exact Home interrupt scope

One executed case passed using two scripted Python JSON-RPC peers. The test
reads an exact target through Home HTTP, rejects a forged session and stale
native turn, interrupts only the selected operation and proves the sibling
turn/session/process remains intact. Only after those assertions does cleanup
interrupt the sibling and close both owned sessions canonically.

Both retained Popen handles prove physical exit. Their observed exit codes are
1, not0; a prior test-only assumption that canonical pipe close must be graceful
was rejected and retained as an antecedent. The final assertion requires actual
physical exit and preserves the codes. Final inventory found no matching fake
Python peers. No personal process was stopped.

This is real SQLite/ASGI/admission/Core dispatch with synthetic native peers,
not browser interaction, provider inference or authentication. Product sources,
ledger and Git were not changed by this task. Counts are overlapping runs of one
case, never multiple independent cases. Ruff passed.
