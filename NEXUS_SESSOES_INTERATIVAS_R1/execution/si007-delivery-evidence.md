# SI-007 delivery evidence

The canonical receipt transaction projects delivery evidence onto the
linked input. Receiving or submitting the command keeps the input in
dispatching. Acceptance, running, pending native input or a successful
turn establishes native acceptance. The canonical operation continues to
carry settlement. Competing turns wait while an accepted input's
operation remains active.

The sender's proven pre-send refusal resolves the input without effect.
Connection loss at `SENDING` or a canonical unknown receipt retains the
same operation and possible-effect flag. Later evidence can reconcile
that same delivery. A lost turn outcome after proven native acceptance
leaves the delivery acknowledged and the canonical turn outcome uncertain.

The projection shares the existing receipt and connection-owner writer
transactions. Existing receipts are preserved. A synthetic SQLite case
checks receipt progression and duplicate short operation IDs on two
executors. Activation still requires capacity acquisition and recovery
for a consumed reservation whose linked attempt failed before sending.

The combined storage, NS-09, dispatch pump and fairness suite passed 32
cases. A focused rerun passed 10 cases after adding the check that native
acceptance does not lift the fence while the canonical turn is active.
