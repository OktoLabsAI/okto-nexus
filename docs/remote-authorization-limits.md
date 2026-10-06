# Remote authorization limits

Connector connection configuration accepts `authorization.minutes: 0` for no
expiration and `authorization.actions: 0` for unlimited actions. Either limit
can be unlimited independently. The optional boolean flags `no_expiry` and
`unlimited_actions` must agree with their respective numeric values.

For example:

```json
{"minutes": 0, "actions": 0, "no_expiry": true, "unlimited_actions": true}
```

Nexus normalizes unlimited values to the internal `null` representation before
validating the Core configuration contract. Finite limits retain their existing
bounds: 1–1440 minutes and 1–1000 actions.

Unlimited limits do not approve a connection. The existing machine and agent
approval flow must complete before an execution grant is created. Grants remain
revocable, and runtime leases and session credentials retain their own lifetimes.
Existing expired grants are not automatically extended by this change.
