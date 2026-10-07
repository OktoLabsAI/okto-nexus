# Global harness MCP inheritance

Requires Nexus 0.2.2, Connector Core 0.0.3 and, for remote hosts, Connector 0.0.2.

In Settings → Global runtime defaults, enable **Include global harness MCPs** to
use MCPs already configured in the runtime host's approved harness directory.
The default is disabled. In Agents → Connections → Harness settings, choose
**Inherit agent/global policy**, **enabled** or **disabled**. The inherited value
is displayed alongside the option. The same setting is available in the Connector
configuration wizard and its harness configuration JSON import/export.

Precedence is explicit harness setting, then agent runtime override, then global
default. `inherit_global_mcps` is a boolean in `/api/v1/runtime-policy`; the agent
policy endpoint also accepts `null` to inherit. In `harness_settings` it is
`"enabled"` or `"disabled"`; omit the key to inherit. Older clients omitting the
new policy field preserve the saved value.

The Server resolves the effective setting into the immutable, hashed opening
payload. Global/agent MCP-default changes do not revoke existing sessions. Editing
an endpoint's harness settings retains the existing workflow: close that
endpoint's sessions, save and authorize execution. A new opening uses the new
choice; previously submitted work is not reconfigured or replayed.

## Host behavior

- Codex and Claude Code retain the approved provider configuration directory,
  including when provider credentials are supplied separately. Without an
  approved directory, enabling inheritance returns a configuration error for
  that agent; the host does not silently inspect a different account.
- The harness loads its own configuration and OAuth state. Native configuration
  precedence and workspace trust still apply, including project MCPs. This is
  not a global-only MCP allowlist. In Codex, opting out explicitly disables
  names from the approved global configuration because CLI tables merge
  recursively; independent project-only MCPs remain subject to Codex's policy.
- Nexus still injects a session-specific MCP entry and scoped credential. The
  Nexus tool approval option grants no automatic approval to third-party tools.
- Only environment variables declared by global MCP definitions are forwarded
  from the runtime host. Restricted variables and Nexus credentials are excluded;
  unrelated ambient secrets are not inherited. File-based credentials remain
  under native harness control. No global config is overwritten or copied to the
  Server, and external credential values never enter launch arguments.
- Pi currently uses the native Nexus tools bridge and has no Core-managed MCP
  configuration adapter. The option is not exposed for Pi and global enablement
  does not change its extensions or native tools.

MCP startup, OAuth expiry and retry behavior remain native-harness concerns.
An external server explicitly configured as required can prevent its own harness
from starting. Such a failure must stay scoped to that agent; it cannot block
other agents through Nexus reconciliation. No successful provider conversation
is inferred from configuration discovery or a transport handshake.

## Validation

Regression coverage exercises global/agent/harness precedence, old-client writes,
per-opening payloads, preservation of active leases when defaults change,
local and remote launch environments with and without explicit provider secrets,
credential filtering, unchanged configuration files, R4 schema/hash validation,
and unchanged Nexus capability injection. Installed Codex checks use disposable
homes: both inheritance modes resolve correctly, and an unavailable optional MCP
does not prevent a new app-server thread. No model turn is sent by these checks.

Native behavior references: [Claude MCP configuration](https://code.claude.com/docs/en/mcp)
and [Codex configuration reference](https://developers.openai.com/codex/config-reference/).
