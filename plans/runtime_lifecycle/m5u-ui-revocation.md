# M5u: real-Pi revocation through the installed UI

On 2026-10-18 the disposable installed Nexus 0.3.1 at `127.0.0.1:8204` used real Pi 0.87.1 through the embedded runtime (`m5l-pi-new`, `m5m-pi-new`) and a separate local Connector 0.0.10 (`m6d-pi`), with Core 0.0.12. The global Nexus listener remained stopped. A copy of the disposable home was made before changes.

Both target paths first returned exact markers through Meta-harness with 1/1 ACK, `read` delivery and `NATIVE_ACCEPTED` outbox acknowledgement: `M5U_REMOTE_BASELINE_OK` from `m6d-pi`, and `M5U_LOCAL_BASELINE_OK` from `m5l-pi-new`.

The operator deactivated `m6d-pi` in Agents. It became Remote / Offline and inactive; the Connector lost its control connection. During that condition, `m5l-pi-new` remained Local / Online and returned exact `M5U_LOCAL_AFTER_REMOTE_REVOKE_OK` with 1/1 ACK, `read` and `NATIVE_ACCEPTED`. Re-activation was confirmed in the UI, but the Connector still reported `AUTH_FAILED` / `CONTROL_DISCONNECTED` during the observation window. No automatic re-authorization after an explicit revoke/reactivate is claimed.

The operator then deactivated `m5l-pi-new`. It became Local / Offline and inactive, and disappeared from the Meta-harness recipient choices. The separate embedded `m5m-pi-new` remained Online and returned exact `M5U_LOCAL_SIBLING_OK` with 1/1 ACK, `read` and `NATIVE_ACCEPTED`.

This is a real-UI revocation/isolation check on both local host modes. It does not exercise an in-flight native effect at the exact revoke instant; that boundary passed in the installed automated M5s slices. The scoped browser, Connector and Nexus processes were stopped. The revocation home was archived under ignored `build/runtime-m6d-ui/home-revocation`; no global process was started.
