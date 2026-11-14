# One explicit expired-grant requery

The first successful canonical review reported the existing unused grant as
available with 239.485913 seconds remaining. This was below our 240-second
two-work window. The first review remains true and is not relabeled expired.
Root explicitly permits one additional **read-only** review after its recorded
expiry, without a new campaign, model reservation, budget or service restart.

The extension requires the exact original available review, product work
checkpoint in `authorization.state=review`, empty successor controller and
successful retained first-review child exit. Clock time permits only querying;
the new canonical response must independently report the same grant expired,
used zero of 20, same scope/actions, before replacing the displayed review.

`authorize_execute_copy.py` differs from the frozen original in one line:
the `pending is None` check becomes the exact retained-prior-review validator.
The extension also explicitly replaces the module's `public_save` callback to
use separate reserved/unconfirmed names and version the current diagnostic.
All parser, canonical transport allowlist, accounting/fence, owner checks and
deadline logic remain. The callback is injected before execute; no original
file changes. The installed `authorization_review` method itself saves the new
review checkpoint; the extension never removes or fabricates that checkpoint.

Before executing the CLI, old public review bytes are copied exclusively to
`authorize-local-review-history-available.json`. Once the new review passes,
the extension reserves a transition with old/new hashes, fsyncs the new bytes,
atomically replaces `authorize-local-review.json`, then writes the replacement
receipt. Failure never replaces the first history with a failed value.

Root command, using the original v13 common proposal/receipt arguments:

```text
<installed-python> -I -B extension.py --manifest <manifest.json> --manifest-sha256 <SHA> <original common args> review
```

Only after exit 0 and a replacement receipt, root reviews the **new** canonical
review and writes the existing exact `authorize-local-reviewed.json` selection.
The prior import supplement's original `apply` remains the sole issue path,
with recover-before-issue and all original CAS/scope/expiry/usage checks.

Run this extension's `verify-exits` plus the prior import supplement's
`verify-exits` before the original final-presence and closure. Retain both
separate ledgers, the old review, replacement receipt and exit sidecars. A
returned failure is not authorization success or an invitation to requery.

Qualification: 17 synthetic cases passed. They cover exact historical state,
clock boundary, no submitted/issued/work fallback, canonical expired/unused
proof, atomic publication and failure preservation, and the installed public
authorization method making only one review POST from an existing review.
No real service, HTTP, grant, credential, provider or model action was run.
