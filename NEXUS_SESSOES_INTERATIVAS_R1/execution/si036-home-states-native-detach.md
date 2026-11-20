# SI-T-I04 Home states across queue, reorientation, detach and results

The installed Nexus, Connector and Core wheels ran with a real Pi 0.87.1
process, a loopback R4 connection, Edge and a Windows ConPTY viewer. The
browser used one tab to inspect the exact session and a second to observe
the live Home board. The session panel intentionally pauses the board in
its own tab. Model responses came from a deterministic local extension
with external network access disabled. [Artifacts and checkpoints](si036-home-states-native-detach.json)

1. **Active** showed the Pi working. Both browser sends returned HTTP 202
   with separate `QUEUED` receipts and no operations linked. The queue
   showed both entries waiting for their next turn. The operator reviewed
   the first entry's text and confirmed reorientation. It kept the same
   input ID and targeted the original run. The other entry stayed queued.
2. The read-only terminal opened and detached while the first turn was
   still held. It restored the console and returned the exact detach
   receipt. After a fresh Home load, the same Pi still showed **Working**.
   **Needs you** showed no request for these messages and **Results** had
   no delivery card at this checkpoint.
3. Before the native boundary, the browser said the reorientation was
   queued for the boundary. It said Pi applied the change after the native
   consumption event. The persisted steer input retained its R4 dispatch
   status. The positive application display came from the separate native
   boundary fact.
4. While the ordinary queued entry ran in its own turn, **Active** showed
   the Pi working and **Results** showed only the first completed turn.
   After the second result, the browser showed two **Response available**
   cards without a verification badge. One card opened by pointer on
   desktop. The transcript contained each of the six exact native entries
   once, grouped under the two original turn operations. The later queue
   receipt reached `ACCEPTED_NATIVE`.

The native history contained exactly three user messages. The Server
recorded one session, one steer, two successful turns and a canonical
close. The probe confirmed the same Pi process until that close and
checked the closed session, detached read-only attachment and database
integrity afterward.

The installed browser probe passed, as did 74 installed backend and
26 Node frontend regressions. The first fixture attempts exposed a missing
test helper import and a missing fixture path. The completed run checked
the three module import paths and the Home asset bytes from the wheel.
This probe covers the observed Windows desktop and Pi flow with simulated
responses. The provider campaign remains open. A different run covers a
real Pi question in **Needs you**. [Native question and operator login](si036-home-question-after-login.md)

This increment changes execution evidence and the ledger. Reverting it
requires no product, data or schema migration.
