# M4d4e3: Server half of the audit handshake

Core `905ad8f` stages an exact, complete registry head with an opaque nonce.
Nexus migration 150 persists the same nonce, revision and digest against the
current reset generation only after the existing startup physical audit and
retained registry import have completed. Conversion of older Core heads runs
in bounded background pages. Nexus repeats the physical directory audit
before staging. A failed Server commit leaves the Core token unpaired; the
retained task retries, while a later boot still performs the full audit.

Validation: 27 selected source and 27 installed Nexus cases passed for store
binding, import, audit-token crash cut, reset and replacement. The installed
Core wheel passed 32 source and 35 installed registry/slot/cost cases, including
100k registrations. The Core wheel SHA-256 is
`19e1e8e4cc78f9d2ac882c858b2866bb1b22e5eba46009601a88796578fd3721`;
the disposable Nexus wheel SHA-256 is
`ebd3d0abf19f597f61012e010883b55d7988706b945ccba1651cdaa6f34415ec`.

The new token is not used for admission. Startup still audits the directory;
there is no claim of reduced startup latency, tested real UI behavior or
global rollout. Connector's independent state half and the anomaly policy
remain pending.
