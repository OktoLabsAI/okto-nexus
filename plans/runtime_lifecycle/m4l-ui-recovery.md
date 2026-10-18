# M4l major UI gate: remote Connector reconnection

Date: 2026-10-18. Isolated wheel installation: Nexus 0.3.1, Core 0.0.12, Connector 0.0.10. Nexus `127.0.0.1:8204`; private Nexus home/workspace and Connector state under `build/runtime-m5v-fresh`. The production/global Nexus on 8202 remained stopped.

1. In Agents, the local Pi was Online. The remote Pi was initially Offline because this old disposable fixture lacked a key and had exhausted its action grant. Regenerated the fixture key through the UI, imported it into the Connector without exposing it in test evidence, and advanced the fixture grant from 20 to 21 actions through the UI. The remote Pi became Online and Connector `CONTROL_READY`.
2. In Meta-harness, sent `M4K_REMOTE_BEFORE_RESTART_OK` to the remote Pi. It was accepted/read and returned the exact marker. The first turn took about 76 seconds. The receipt view initially showed 0/1 while pending; after refresh the timeline showed 1/1 and the reply.
3. Restarted only this Nexus. Connector reported `CREDENTIAL_REPLACEMENT_REQUIRED` rather than reconnecting. Root cause and Connector fix: [ticket recovery report](../../../okto-nexus-connector/plans/runtime-lifecycle-m4l-ticket-replacement.md). No Nexus source change was required.
4. Installed the corrected Connector wheel and sent `M4L_REMOTE_AFTER_RESTART_OK` through Meta-harness. The operator message became accepted/read and the remote Pi returned the exact marker. The timeline showed 1/1 acknowledgement and the reply.
5. Restarted the disposable Nexus a second time before the active ticket expired. Connector rejoined automatically at 13:31:11 UTC with `CONTROL_READY` and `CONNECTED`; Agents displayed the remote Pi Online.

This qualifies the major real UI gate for remote delivery and Nexus restart recovery. It does not qualify the pending >4096-row historical checkpoint backfill, physical directory admission audit, or controlled global rollout. The disposable fixture is stopped after the test.
