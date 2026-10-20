# M5b — Remote preparation failure isolated to one session

Status: selected installed qualification passed; joint UI milestone and full M5
remain open. 2026-10-17.

The Connector previously treated a native preparation error (including Pi's
version-probe timeout) as a failure of its whole R4 control connection. A
healthy sibling could become unavailable while the pending opening had never
entered Core native admission.

After a `NativeAdapterError` from `runtime.prepare`, the Connector now stops
the exact session's renewal, joins it, contains that runtime and native action
owner, and checks that the Core journal has no session claim. It persists the
scoped startup-refusal association, releases only the correlated consumed
capacity reservation, then commits a terminal no-effect Core receipt. If the
release or proof cannot be established, it does not claim success or reusable
capacity. The Server accepts the receipt only for the current authorized
dispatch and a pending, event-free opening. It closes that session and marks
the associated delivery failed in the same transaction; another session or
agent is unaffected. Affinity checks exclude a closed, proved preparation
failure so later handoffs can proceed.

The local Connector in a separate process reproduced a failed preparation
followed by a successful new handoff on the same control connection. The first
capacity reservation became RELEASED, the first session CLOSED and the first
delivery FAILED_FINAL; the second session opened and its turn reached
SUBMITTED. A Connector unit test also kept an already open healthy sibling
responsive through a preparation failure for Pi, Claude and Codex. Forged
receipt flags and a wrong connection generation were rejected by Server tests.

Installed qualification: Connector 54/54 and Nexus 17/17 selected cases passed
on Windows; all three installed package trees matched their wheels byte for
byte (161 Core, 99 Connector and 547 Nexus package files). Both campaigns
recorded no changed inputs. `pip check` found no broken dependency. Wheel
hashes and JUnit hashes are in [m5b-results.json](m5b-results.json).

This checkpoint addresses native preparation errors after a valid initial
lease. Other startup stages, uncertain native effects, storage-unavailable
retries, differential reset/reconnect behavior, load qualification and the
large-milestone real UI gate remain. The current global Nexus installation
was not changed by this qualification.
