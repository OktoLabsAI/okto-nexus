# Public R4 session observation

GET /v1/runtime/sessions/{session_id} now returns the normative SessionView
shape. An optional executor_id disambiguates a session ID shared by executors.
Unknown or repeated query parameters are rejected.

The canonical runtime authentication service verifies the current credential
inside the read transaction. The session subject and the recorded opening actor
can read their history; a verified operator can inspect other subjects.
An unrelated ordinary agent receives 404. Multiple visible matches produce 409.

The view combines the admitted opening scope, canonical session lifecycle,
current executor connection generation, latest persisted lease, close intent
and receipt observation timestamp. An elapsed active lease is projected as
EXPIRED. Control availability is false for expired leases, owner/connection
generation mismatches, disconnected or revoked executors and closed sessions.
This observation is not an authorization token; mutations still pass admission.

No process handle, filesystem path, provider configuration, ownership proof or
credential is returned. Process state and ownership remain UNKNOWN because the
current Server projection does not contain independently verified process
observations. In particular, CLOSED does not imply the process exited: an
attached runtime may have been released. Release-pending currently describes an
admitted close that has not produced the canonical CLOSED lifecycle.

The installed campaign covers a normal open/close, no-store/schema conformance,
operator/subject/foreign scope, missing authentication, invalid query,
expiration, connection-generation drift, disconnection, and ambiguous session
IDs. Reads do not create another operation or runtime.

This increment does not close M10. Remaining fixed-plan work includes complete
process/ownership observation, CLI/UI consumption, session reuse, retention,
and the other milestone criteria. See the session-view evidence index.
