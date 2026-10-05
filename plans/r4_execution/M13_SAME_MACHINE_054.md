# Core .54 same-machine native acceptance

The user explicitly reserved independent-machine acceptance for a manual session
with their participation. Current campaigns exercise this Windows machine with
separate Server and Connector processes over real loopback HTTP/WSS. They do not
close the independent-host gate or replace the remaining UI/platform matrix.

## Claude remote CLI cycle

With the discovery .54 artifact tuple recorded in M03_DISCOVERY_PRESENCE.md,
`test_real_provider_through_public_connector_cli[claude_stream]` passed in
220.19 seconds. The installed runner verified all three package trees and unchanged
inputs. Public CLI onboarding registered the executor, selected the installation,
realized the workspace, applied consent and opened the real native provider.
The lease reached serial 2 before the turn. Three explicit scoped native approvals
were applied; the turn succeeded, handoff work became COMPLETED, and close succeeded.
Server and daemon exited with code 0 and campaign credentials were removed.

Evidence: `evidence/native-054-connector-claude-keyring/` (campaign, installed-byte
verification, JUnit and native reports). The preceding attempt in
`evidence/native-054-connector-claude/` stopped at identity import because the
environment lacked the optional `keyring>=25,<26` dependency. Installing that
declared extra activated Windows WinVaultKeyring; no plaintext fallback was used
for the successful native campaign. Neither application bytes nor authority tests
were altered to obtain the pass.

This is one actual-provider, same-machine CLI journey. Remaining providers,
embedded execution, recovery, full UI and final artifact/CI qualification remain
open. No G0–G3 closure is claimed.
