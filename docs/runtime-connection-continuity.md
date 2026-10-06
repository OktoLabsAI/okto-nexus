# Remote runtime connection continuity

An updated Connector negotiates connection continuity with Nexus. Ticket
renewal then happens on the existing WebSocket. Nexus revalidates current
authority and extends the bootstrap and attached lane tickets atomically.
It keeps the same connection ID, generation, lane attempts, native sessions,
and execution leases. Revoked or expired authority is never renewed.

Both peers monitor liveness: Nexus expects inbound traffic within 30 seconds;
the Connector sends heartbeats every 15 seconds and expects inbound traffic
within two heartbeat intervals. Nexus acknowledges negotiated heartbeats.

After a short transport loss, Nexus allows the same ticket and connection owner
to resume for up to 30 seconds. The Connector makes a bounded fast-resume
attempt before its normal reconnect lifecycle. A pending control request with
an uncertain result disables fast resume and requires durable reconciliation.
Lease expiration still contains native execution if recovery cannot finish.

An authorization change closes the socket with code 4403 and a fixed reason,
instead of reporting the dispatch failure as a generic 1011. Actual server
storage/internal failures retain 1011. Logs never include credential material.

Older peers retain their previous reconnect behavior. Install the matching
updated Core, Connector, and Nexus to enable all continuity capabilities.
