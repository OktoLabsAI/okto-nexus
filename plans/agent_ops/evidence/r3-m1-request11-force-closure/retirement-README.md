# Request11 retirement: read-only point-in-time projection

Request11 already has a version1 failed_open retirement checkpoint, revision13.
Its session is FAILED/CLOSED; agent recovery is READY in connection generation6.
The canonical session stream field is null, while the local stream row is present.
No raw checkpoint, journal, authentication material or database bytes were copied.

A later owner revalidates store/slots and the old-generation agent recovery row.
Retired request11 is excluded from pending local records unless a real outstanding
slot invalidates its checkpoint. Terminal sessions/operations are not replayed.
Wait for canonical READY in the new generation before considering new work;
do not treat current READY or this note as proof that a restart/recovery occurred.

No new retirement fix is indicated by this observation. Manual recovery-plan and
confirm-stopped are for outstanding scoped historical resources, not routine
cleanup of an already retired failed session. They cannot override stopping or
inherit an old owner's in-memory proof. The plan GET itself writes a maintenance
audit and was not called. No service, POST, database write or model call occurred.
