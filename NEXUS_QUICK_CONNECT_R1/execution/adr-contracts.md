# QC-00 frozen contracts

## Grammar, CWD and output

`connect [harness] [project-name] [--id ID]`; root aliases are exactly the
supported CLIENTS names and invoke the same function. Product commands win.
One positional always means harness, including beside --client. Matching
duplicate selectors are allowed; contradictions and unsupported participant
syntax fail before service/configuration/vault/network reads. No argparse
abbreviations. JSON and non-TTY never call input or chat. New noninteractive
additions still need the stable --profile idempotency checkpoint.

Capture invocation CWD once; --project remains an explicit path. Compare roots
with existing canonical utilities and directory evidence, never global lowercase.
Precedence is concordant explicit choice, validated Nexus mapping, unambiguous
local Git origin hint, working-tree basename, physical-root basename. Neither
name nor URL identifies a workspace. Retained intent freezes the name hint;
recover it before discovering Git or examining collisions. --plan/help/grammar
errors never start Git or a harness; plan never starts the daemon or reserves.

Pure frozen DTOs live in `domain/quick_connect.py`. Only the public key
`connect_id` identifies this feature. QuickConnectOutcome version 1 allows
connected only with a normalized ID, bound state and revalidated full canonical
reference. Plan uses proposed_connect_id. Configured without work is still
session not_checked and work not_submitted. Output precedes optional chat.

## Namespace, reservation and Finish

The normalized ID is ASCII `[A-Za-z][A-Za-z0-9_-]{0,63}`, lowercased without
truncation. Uniqueness is `(server_id, workspace_id, connect_id)` across agents,
hosts and adapters. Reserved/bound/retired rows survive event cleanup. A same
name is never proof of retry ownership. Prior own receipts/checkpoints precede
collision handling; changed root/harness/ID is not the same intent.

The optional product setup envelope is:

```json
{"public_connection":{"version":1,"connect_id":"reviewer","reservation_ref":"pcr_<32hex>","project_revision":"sha256:<64hex>"}}
```

workspace_id remains in the existing request. Omitted public_connection is
removed before legacy request hashing, with no synthetic null/default. The
stable reservation_ref is generated before review and included in the hash.
After exact approval and inventory/version confirmation, reserve the complete
request using POST `/connections/public-ids/reserve` with approved:true. This
happens before model Test. Save the response separately, without modifying the
approved envelope. Lost replies are retried by the same actor, intent, ref and
request hash; changed content is refused.

Finish validates the retained reservation, binds its ID to the full immutable
tuple, and writes that ID into the receipt inside the existing outer transaction
alongside workspace, agent, binding and grant. Rollback cannot leave a bound ID
or new grant behind. Prior committed receipts are checked first.

A new project uses a Server-private opaque draft namespace backed by canonical
executor/directory identity and reviewed label/revision, never a fabricated
workspace ID or a client-path-only namespace. Concurrent first connections to
the same directory must re-resolve/re-review rather than silently duplicating or
coalescing projects. An uncertain reservation is not released by elapsed TTL.

Authorized GET public-ids is passive; capability detection fails explicitly on
old Servers. Explicit associate-existing binds only metadata using the exact
binding tuple/revision and an approved idempotent intent; no Test, Finish, grant,
agent creation or alias rewrite. An unavailable/replaced occupant keeps its name;
no implicit transfer. Unauthorized collisions disclose no occupant details.

After a confirmed Server commit, local shortcut write failure is
configured_shortcut_pending. Recovery repairs that shortcut only. It never
compensates by deleting canonical configuration or issuing another Test.

## Compatibility and locks

Home R3 `harness_id` already means adapter family. Preserve that field unchanged;
new connect_id is nullable metadata in authorized catalogs/Home refs and UI.
Old configuration.alias, agent/binding/session IDs, profile and Project assistant
role keep their meanings. Existing URLs, grouping, controls and contextual panel
remain. No Core/Connector redesign or new per-ID daemon is authorized.

Local lock order stays PROFILE.guard then short catalog.guard. Server UoW is a
short independent transaction; never hold the local catalog lock across input,
HTTP/provider waits or another profile lock. Review and apply still use existing
setup/checkpoints/receipt authority. Remote operator CWD/Git cannot redefine a
Connector root; remote failures cannot start a substitute local Server.

Git adapter budget: aggregate 2 seconds, at most 6 child calls, combined bounded
stdout/stderr at most 64 KiB per call (384 KiB aggregate maximum). Only trusted
absolute Git, local rev-parse/config without includes/system/global overrides,
shell=False and closed stdin. No URL/stderr survives into safe DTOs. No network,
safe.directory changes, hooks, helpers, installation, branch authority or root
expansion. Tests of fixtures are not real harness qualification.
