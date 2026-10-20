# M4d4e — verified registry frontier protocol

Status: design for the next implementation cut; no startup-scan removal is
authorized by this document. M4d4d imports physical names but deliberately
keeps the existing full startup audit.

## Authority and persistence

The physical ledger owns its immutable `store_id`, journal registrations and
their monotonically increasing revisions. Server stores the `store_id` it has
accepted for each reset generation. Connector stores its accepted `store_id`
in independent atomic state. A trusted host, never a tool payload, supplies
physical names and session scope to Core.

M4d4e1 adds a Core-owned registry head containing `(store_id, revision, digest,
complete)`.
Every new registration updates the digest in the same SQLite transaction as
the immutable row. The digest is a deterministic chain over the previous
digest, revision, canonical basename and exact session scope; idempotent
re-registration leaves it unchanged. A bounded, resumable conversion computes
the head for pre-existing registrations before any host may use it as an audit
proof. Core returns the head with bounded indexed reads and rejects a missing or inconsistent
head. This is registry integrity metadata, not proof that journal files exist
or that native processes stopped.

The M4d4e1 installed Core wheel passed 21 registry/cost cases at 1k, 10k and
100k registrations; the head read used 35 SQLite VM steps in each case.
Another 43 installed slot/capacity cases passed. The cross-store nonce and
host admission protocol below remain design, not implemented behavior. Nexus
composition with that installed Core passed 27 selected binding, import, reset
and catalog-cost cases with up to 10k historical sessions.

M4d4e2 now provides the Core token stage, and M4d4e3 records the matching
token in Nexus reset-generation storage after background import and a repeated
physical audit. Neither component consumes that token to bypass startup audit.
M4d4e4 persists the matching token in Connector schema 15 from a retained
background worker. The Connector still has one shared journal, and its token
is likewise not used to bypass admission. The anomaly policy and partial
restore matrix remain open.

M4d4e5 now fences a definite same-identity Core rollback before Nexus or
Connector admission, while allowing a newer Core head to proceed only through
the unchanged full physical audit. Proving that a newer head extends a stored
host anchor remains an open gate.

M4d4e6 adds sparse Core digest checkpoints and an exact bounded prefix read.
Both hosts now verify that a forward Core head extends their prior digest
before renewing the token. This does not answer whether the physical directory
changed while the host was stopped, so admission still uses the full audit.

After the initial full physical audit and M4d4d import have completed, Server
commits its first frontier with the exact Core head and a fresh audit nonce.
Core durably records the same nonce/head in its ledger before Server commits
the frontier; a crash between those commits leaves Server without a usable
frontier and repeats the audit. Connector follows the analogous two-store
protocol with its locked state snapshot. Neither host may infer an empty store
from a missing ledger when it has retained execution history or a prior
binding.

## Startup and background audit

With a matching cross-store nonce and head, startup reads the Core registry
head and bounded pages of registrations after the pinned revision. It checks
new names against exact canonical Server or Connector ownership before
admitting their subjects. Occupied physical slots, pending native claims and
unsettled publications are still reconciled independently; an audit frontier
cannot override them. A restored Core ledger with the same identity but an
older or divergent head fails closed. A restored Server/Connector snapshot
without the matching nonce returns to the first-audit path.

The file directory cannot be proven unchanged while Nexus is stopped without
reading it or relying on an external durable filesystem event source. The
optimized startup therefore needs an explicit, bounded background directory
audit and a policy for the interval before it finishes. It may only admit
work for subjects whose known resource ownership is independently proven;
an unattributable physical anomaly fences the shared host when discovered.
Do not remove the full startup scan until this residual interval and its
fault-injection tests are accepted. A mere `registry_import_complete` bit is
not an audit frontier.

M4d4f1 measured the existing physical name scan up to 100k files. In the
current trust model, the registry/token cannot attest offline filesystem
changes; the full name scan remains an admission prerequisite. The next
implementation should shorten and isolate this scan or adopt a physical layout
whose ownership can be audited independently, rather than treating a matching
database digest as physical proof. See `m4d4f1-physical-audit-measurement.md`.

## Required qualification

- Crash after each of: Core row registration, registry-head update, Core nonce
  commit, Server/Connector nonce commit, physical journal creation and scan
  checkpoint. Resume with identical identities and no duplicate native claim.
- Restore Server, Connector or Core alone to earlier snapshots, including a
  same-identity ledger fork with equal revision but different registrations.
- Missing/corrupt registry/head, sidecars, unregistered physical files,
  registered-but-absent journals, disk-full/locked writes and owner replacement
  preserve evidence and expose a technical diagnosis.
- Measure conversion once and later boots separately at 1k/10k/100k retained
  sessions. Include registry, reservations, claims and slot metadata under the
  same configured Core storage limit. Measure SQL work and opened files, not
  only wall time.
- Run the qualified change in a disposable installed Nexus UI campaign with
  Pi, Claude and Codex plus a separate local Connector process. The real UI
  gate remains distinct from focused storage tests.
