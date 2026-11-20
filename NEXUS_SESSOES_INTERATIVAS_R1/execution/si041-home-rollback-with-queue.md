# SI-041 switch Home with work in the queue

On Windows, an authenticated Edge 157 browser used the installed Nexus
bundle with a real Connector daemon and Pi 0.87.1. The two services exchanged
R4 frames over loopback. A deterministic provider held both native responses
at separate barriers with external networking disabled. [Package digests and checks](si041-home-rollback-with-queue.json)

1. The first turn was in progress. The browser used **Add to next turn** for
   a second message and received HTTP 202 with a `QUEUED` receipt. The
   stored input had no operation linked to it.
2. The browser selected **Use classic Home** in Settings. The exact input
   row, first operation, Connector generation and Pi process were preserved.
   The browser made no extra input POST.
3. While Classic Home remained selected, the first turn completed and the
   same input ID and sequence moved into dispatch under a new turn operation
   on the original session. The test observed `DISPATCHING` with consumed
   capacity and checked Classic Home before releasing the second response.
   The receipt then reached `ACCEPTED_NATIVE`.
4. Back in operational Home, both prompts and both results appeared once
   in the same conversation. The native journal contained two user messages
   in order. The browser had made one queue submission. Canonical close
   retired the session and the original process exited.

The installed end-to-end scenario passed. An earlier test fixture used the
wrong field to read the Connector generation. The final test observed the
retained Classic view before manually releasing the simulated second reply.
R4 submission alone did not advance the receipt to native acceptance.

This covers the per-browser rollback with a live Connector and native Pi.
The Server feature flag remained enabled. The external-provider campaign
required by SI-T-I03 is open. The increment changes evidence and the ledger.
Reverting these records requires no database or runtime rollback.
