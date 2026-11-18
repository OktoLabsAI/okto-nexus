# SI-014 dashboard queue and cancellation API

The dashboard can read FIFO metadata for one exact session and owner generation under a current human login. A bounded queue page carries its queue revision, pause state and continuation cursor. A pending-only filter excludes accepted, expired and cancelled entries. The cursor is scoped to the full session and filter. It is a continuation marker. Every request rechecks the login and canonical scope.

The read returns no message text, client intent or human authority reference. An operator who has just signed in can read metadata without creating a durable author reference. Only the original login and surface can remove an unsent entry. The cancellation route requires both the input and queue revisions and reuses the existing writer and authority fence. It performs a local state change and preserves the entry in the receipt history.

The focused Python run passed 25 cases. The new HTTP test uses the running application with a temporary database and synthetic native peer. During an active turn it checks metadata-only pagination, scope and filter isolation, cross-origin refusal, author and surface eligibility from the scoped view, logout, stale revisions and successful removal. The synthetic peer recorded only the original active turn. Existing SQLite coverage verifies the author and surface distinction and read-only projections. Ruff passed for the changed Python files.

The cancellation route requires the existing opt-in interaction setting. There is no schema change. Reverting the dashboard routes preserves durable inputs and cancellation records. The queue UI, pause and resume controls, exact interrupt, steer confirmation and real harness evidence remain pending for SI-014.
