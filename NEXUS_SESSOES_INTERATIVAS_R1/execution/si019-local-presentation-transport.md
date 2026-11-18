# SI-019 local presentation transport

The dashboard runtime router now has local prepare, stream and detach endpoints. The Server issues a short one-use ticket with a live human login. The socket needs both that ticket in the Authorization header and the operator session cookie. It validates local peer and host, transport security, Origin, subprotocol, exact scope and owner generation before accepting a challenge reply. A browser from another origin and requests carrying proxy forwarding headers cannot reach the handshake. Separate logins for the same operator have separate authority references.

The channel currently serves the exact Codex turns and items pages. It renews only its presentation lease and detaches its own attachment on logout, disconnect, unsupported frames or explicit detachment. Request and response frames are bounded. The transport never calls a native close, creates a work operation or issues a productive lease.

Tests exercise a real SQLite attachment broker and operator session store. They cover one-use tickets, challenge failure, wrong scope, another login, origin and forwarding rejection, logout while idle, explicit detach and rejection of a native productive method. A separate Uvicorn test exercises HTTP preparation and the challenge and history exchange on an actual loopback socket, followed by socket EOF and a durable detach receipt. The tests use synthetic owner and history data.

149 session interaction and embedded runtime regression tests passed. The separate loopback network test passed on the final test code. Ruff and strict archive validation passed, and the packaged transport matches the source.

The app returns unavailable until an eligible Codex owner and capability are installed in the local presentation service. The transport exposes read-only history at this stage. Native TUI bootstrap, the CLI relay, writer support, remote transport and the remaining adapter qualification are still open. There is no new migration. Restoring the previous schema-180 application build removes these endpoints and retains their records.
