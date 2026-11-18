# SI-006 human authority

The operator auth database gains one additive relation. A signed-in
operator's existing cookie can resolve to a random opaque reference tied to
that login. The reference survives restart and cannot authenticate as a
cookie. Logout invalidates that exact login. Expiration and account
rotation also make the reference unusable. The public auth response and
session rows keep their existing format.

The authority fence holds the auth database writer lock across a caller's
execution claim transaction, with checks against the current clock. The
lock order is auth database first, execution database second. A caller
releases both before contacting the native owner. A separate runtime grant
and effective lease still govern the productive effect.

The combined operator-auth and session-authority regression passed 13
cases in the isolated Nexus/Core prefix. It covered exact logout,
restart, account rotation, expiry during a fence and exclusion of a
competing SQLite writer. It used a temporary account. The dispatcher
does not acquire this fence yet. No API exposes or consumes the reference
for session input. The new relation can remain after returning to an
earlier binary. The global installation was not migrated.
