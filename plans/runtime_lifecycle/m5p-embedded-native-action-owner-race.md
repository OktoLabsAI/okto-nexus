# M5p: committed embedded native action across owner replacement

An isolated installed Pi session used the actual Nexus native-action bridge to claim a handoff. The test held the bridge response *after* the Server committed the claim, then failed the embedded execution owner. While the response was held, the old owner remained in place, the handoff was `CLAIMED` at epoch 1 and exactly one `handoff.claimed` event existed. After releasing the response, the old owner drained and its native process stopped before the successor took ownership.

The caller received claim epoch 1. The Server retained one native-action receipt and one claim event. The old capability was removed from the local vault; a direct request using its captured material after replacement was denied by the Server because the original session was no longer active. The capability row need not be explicitly revoked for this denial: session/lease authority is rechecked on every action. The same test passed against source and isolated installed wheels (16.89s and 15.94s). No production code changed or global Nexus process was started.

This covers the embedded Pi post-commit native-action/owner-replacement boundary. The corresponding Connector process boundary and pre-commit uncertainty remain within the existing M5 native-action matrix.
