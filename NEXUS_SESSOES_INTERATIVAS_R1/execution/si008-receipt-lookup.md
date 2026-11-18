# SI-008 read-only receipt recovery

The service reads a single retained receipt by the original client intent
and author reference. It checks the current human login and the canonical
session reader under one execution read transaction. Executor, binding,
workspace, agent, surface and stored input generation all scope the lookup.
An earlier generation remains readable when the same canonical scope is
visible. Missing and mismatched data return the same result.

The receipt returns only delivery state, revisions, sequence, operation ID
and possible effect. It contains neither the submitted body nor credentials.
Four migrated SQLite fixture cases passed, including real temporary operator
login and logout, wrong author or scope, earlier generation and a read-only
connection. The service has no HTTP route yet.
