# M4d4d — bounded legacy journal registry conversion

Status: selected source and installed validation passed. This is an incremental
conversion checkpoint, **not** the verified audit frontier.

After Nexus validates and binds the physical Core ledger, it imports existing
physical per-session journal names into Core's immutable location registry.
Each page resolves at most 128 names against indexed canonical Server session
metadata and registers the exact `(server, executor, session)` location. A
durable flag on the Server's generation binding is set only after the entire
directory pass succeeds. Crash or storage failure leaves the flag unset;
registrations already committed in Core are idempotent on retry. A conflicting
physical registration or missing canonical Server identity keeps the flag
pending and preserves the evidence.

The existing full startup directory audit remains required. Conversion itself
runs as retained background maintenance after agent readiness, with bounded
pages and a short yield between Core writes so it does not serialize agent
admission behind historical registrations. The owner joins this producer
before closing the physical ledger. Neither a completed import flag nor this
checkpoint authorizes skipping the startup scan; the frontier, background
audit, crash matrix and combined metadata budget remain separate work.

Source evidence: nine focused binding/conversion/catalog cases passed after
the initial implementation; 12 real-composition, initial-refusal and reset
cases passed after moving conversion behind readiness. The new shutdown join
case passed separately. The installed Nexus `0.3.1` wheel (574 package files,
SHA-256 `a0fff54cf52a700cb75c2eec58aba2da73b47d49945d3750e784313cee0fdfc5`)
was checked byte for byte in a disposable environment alongside Core `0.0.12`
(162 files, `1d5bdb7a510ad0ad1b8767a156ed3d8c7a042425809227217c0dd46d1eb294ae`)
and Connector `0.0.10` (101 files,
`a687bebfaac5b9e7d205725f537a15534cd9f790bfc981441243910b9b17a18a`).
The final installed campaign passed 11 cases in 141.44 seconds
(`build/m4d4d-installed.xml`): exact binding, interrupted and shutdown-held
multi-page import, all three local composition adapters, and both preserved
agent reset variants. The global installation remains untouched at this
technical checkpoint.

The 100,000-session post-change cost and mixed Core ledger space budget have
not been measured. The import flag must not be used to bypass startup audit;
that requires a separate verified frontier and background anomaly policy.
