# Self connection discovery and endpoint setup — surface 60

Follow-up to the operator request on feature/v0.2.0. Identity docs version27;
connection discovery contract_version1; additive REST/MCP actions, no new table
or migration. Existing native adapters, shared open service, owner proxy and
logical inbox/handoff semantics remain in place.

## Operator workflow in Agents

1. Open **Connections** on the existing agent card. Enable the intended methods
   and save the policy. Expiry controls use the same field styling as Agents,
   including light/dark surfaces, borders and focus states.
2. Click **Configure endpoint**. Select the connection method, endpoint name and
   absolute project directory on the Nexus server. For managed runtimes, select
   an existing approved compatible profile or create an isolated profile with
   an optional executable and supported advanced configuration. New profiles do
   not inherit the operator environment. Configure the intended provider/tool
   home explicitly when required; do not paste provider tokens into JSON.
3. Explicitly check the approval box and click **Create approved endpoint**.
   This configures the endpoint without opening a process or enabling boot.
   Attach requires a supported host and an explicitly approved session PID;
   Windows does not acquire unsupported native attach capabilities.
4. For MCP, ensure the agent has its own Nexus API key, then select **Authorize
   MCP opening (1 hour)**. This issues only discover/open permission, never send
   or execute_work. The existing authorization, canonical permissions and grant
   expiry still apply. Renew explicitly when needed.
5. For a harness without MCP, select **Generate connection command**. Choose
   PowerShell, Bash/cURL or Request JSON, then **Copy connection command**.
   The scoped credential is transient, shown only after issuance; closing or
   revoking clears it. The command targets the current Nexus origin and POSTs
   an empty body to the existing limited opening route. Identity/process options
   cannot be supplied through the payload. Repeating the same command retains
   the durable opening identity; it does not authorize another native start.

Profile creation and endpoint creation reuse the existing administration APIs.
If profile creation succeeds but endpoint creation fails, the UI retains that
profile for a corrected retry. It never deletes records or starts a runtime to
roll back setup. A disabled method stays disabled until explicitly enabled.

## Agent workflow through MCP (HTTP or stdio)

Authenticate using the agent's own Nexus API key and call:

```json
{"view":"connections","maintenance":{"action":"available"}}
```

on `harness_list`. The response identifies the authenticated agent and shows its
methods, configuration readiness, own endpoints, unavailable_reasons and a
connect instruction for eligible endpoints. It accepts no payload agent_id and
exposes no project paths, profile configuration, secret references or credentials.
Own method configuration may be inspected without an open grant; opening still
requires the operator-issued grant and current canonical permissions.

Use the returned instruction with a unique identifier for this opening:

```json
{"view":"connections","maintenance":{"action":"connect","endpoint_id":"own-approved-endpoint","idempotency_key":"my-opening-001"}}
```

REST equivalents use the same authenticated service:
- `GET /api/v1/connections/available`
- `POST /api/v1/connections/connect` with endpoint_id and idempotency_key.

`available` means configuration, platform, owner lease and authorization permit
requesting an opening. It is not a binary/provider probe or a guarantee that
capacity and external conditions cannot change. Admission is rechecked on use.
Authorization is revalidated before marking native effects and again before
persisting the ready session; revocation during startup causes refusal/cleanup.
The callback performs only local authorization/storage operations inside the
existing transaction; external start remains outside it. Pending/uncertain
requests are never automatically replayed. No new migration is necessary.

HTTP MCP uses the current serve owner. Authenticated stdio forwards through the
existing owner client and only with the same principal's configured key; another
agent/operator key cannot be substituted. A missing/disabled method, revoked
grant, inactive identity, changed profile or unauthorized endpoint is denied.
An operator's full connection list/configuration remains operator-only.

## Remote operation boundaries

Agents may reach a remote Nexus using MCP over HTTP or the authenticated HTTP
API, including a harness without MCP that can execute the copied command. Pi,
Codex and Claude stream runtimes start on the **Nexus server**, with its approved
executable/profile/project. This does not adopt an existing local conversation
or provide a bridge from a harness on a different machine. Attach uses the
approved session accessible to that host. Native stdio/RPC/socket adapters are
not converted into HTTP protocols by this change.

## Evidence and application

See [self-connections.json](evidence/self-connections.json) for source SHAs,
commands, test results, package hashes and rollout status. Tests use disposable
stores, synthetic connector peers and isolated Edge. No actual provider/model
was invoked in this follow-up. The browser campaign executes the copied
PowerShell command against its fixture HTTP server and verifies the canonical
agent and single runtime. Protected pre-existing static working-tree files are
preserved; clean Git/package assets carry the new UI.
