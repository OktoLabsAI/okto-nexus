# Optional project preset updates

Normal `connect` and package upgrades preserve existing project settings. Use
`preset` only when you want to review adoption or a newer recommendation:

```text
okto-nexus preset --profile project --plan
okto-nexus preset --profile project --approve <displayed-review-revision>
```

The current recommendation is `project-generalist`, revision 1. A connection
already recording this revision reports `up_to_date`; its customized values are
not reset to match defaults. Future revisions use the same explicit review path.
An existing connection without a preset origin can adopt the current origin
while preserving its existing choices; the ordinary setup effects below still
require approval.

The command uses the existing saved project identity/binding. `--plan` reads the
canonical Server state and saves a review checkpoint inside that project profile.
It does not start services, run executable probes, open a harness, apply settings
or issue authority. For a remote operator profile, authenticated reads use the
existing protected human session. The Connector keeps its own participant
credential and host configuration.

## Review and application

The review compares current values with the defaults recorded for the previous
preset revision. It proposes a new value only when the old default is still in
place. Customized values, including individual harness settings, stay intact.
An unchanged field removed from a later preset returns to the harness default;
a customized value remains. Legacy revision-1 receipts use the immutable known
revision-1 base. An unknown historical base or a newer-than-supported stored
revision requires inspection, never a guessed reset or downgrade.

The diff covers runtime enablement, session policy, harness settings, Nexus tool
access and authorization limits. Identity, name, role, coordination permissions,
MCP servers, host paths, credentials, agent execution-location preference and
Server-wide policy are preserved. Existing dashboard controls still edit these
same canonical objects when you explicitly choose further personalization.

Read all effects before approving:

- Runtime/session policy changes can invalidate grants and boot approvals on
  **every connection of this identity**. Endpoint settings can invalidate the
  selected connection's consent. The review lists affected connections, grant
  IDs and boot approvals; they are rechecked before commit.
- With runtime enabled, ordinary Finish issues a new execution grant only for
  the selected connection, using the displayed actions and time/action limits.
  Revoked grants and disabled boot approvals are not restored. Other affected
  connections require their own explicit authorization.
- An active local execution binding uses the existing version check and model
  connection test before Finish. The test may incur provider usage. Existing
  sessions may need explicit closure or reconciliation; the command does not
  close them automatically. Applying through a local operator profile may start
  or reuse its configured Server service, without installing a service.
- An approved remote Connector binding changes through the Server's existing
  Finish transaction. It does not run a host probe/test, alter remote paths or
  submit work. A remote Server failure never creates a local substitute.
- A personalized disabled-runtime choice remains disabled. Its settings can be
  updated, but no harness test or execution grant is issued.

Every new update revalidates the exact configuration, preset defaults, current
operator authority, binding, agent state and affected execution authority.
Changing a path, MCP configuration, auto-claim policy or other unreviewed field
cannot be hidden in the update request. Late failures roll back configuration,
grant changes and the receipt together.

## Recovery and concurrent changes

The original project association remains intact. The update retains its own
request ID in the same profile before Test/Finish. To recover an approved update:

```text
okto-nexus preset --profile project
```

A lost Finish reply recovers the canonical receipt without another model test
or grant. Receipts from older preset revisions remain readable after an upgrade.
If a submitted test can no longer be confirmed, the command preserves uncertainty
instead of running it again. Inspect that retained setup on the Server; `--refresh`
cannot discard an uncertain approved operation.

An unapproved review, a confirmed Server refusal with no committed effect, or a
failed connection test whose cleanup is confirmed can be replaced explicitly:

```text
okto-nexus preset --profile project --refresh --plan
```

Review the new revision and approve it separately. EOF/declining approval makes
no configuration change. Ctrl+C stops observation without cancelling an owned
test or committed setup. `--json` never accepts a review implicitly.

Exit codes: `0` for a saved plan, current revision, declined interactive review or
completed update; `2` for invalid arguments; `3` for required approval, refusal,
unready service or unconfirmed result; `130` for Ctrl+C. The command submits no
project task; use `work` for productive activity.
