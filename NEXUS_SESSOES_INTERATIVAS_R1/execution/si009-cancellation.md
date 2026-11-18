# SI-009 cancel one owned input

The cancellation boundary uses the active human login fence and the exact
input author, surface, session scope, owner generation and current
cancellation capability. Both input and queue revisions participate in
the CAS. Only QUEUED and PAUSED rows without a linked operation or possible
effect can become CANCELLED. The original content and history, queued
successors and current runtime work are preserved.

An existing PREPARED capacity attempt remains durable when cancellation
wins, and SI-008 can release the fenced reservation by its original ID.
When R4 staging wins, cancellation is refused. The action does not need
a productive execution grant.

Thirteen fixture cases cover current login, two logins for the same
operator, stale scope and revisions, eligible states, and both SQLite
writer outcomes in the staging race. No schema change. Public HTTP and
the queue UI remain pending.
