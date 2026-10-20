# M5a — Shared startup refusal and consumer qualification

Core checkpoint `19bb8f2` on `feature/v0.0.12` provides the journal fence for a
current host's preparation failure. It preserves the original operation ID and
does not invent physical release, a lease denial or a session claim. Its 149
installed contract cases passed; the implementation/evidence are in Core's
`plans/runtime-lifecycle-m5a.md`. M5 is in progress, not complete.

The preopen bundle's base-schema hash was stale after inventory format 3.
The previous installed Core rejected this bundle with `CONTRACT_BUNDLE_INVALID`.
The new artifact repairs that manifest and tests reconciliation-branch
equivalence. The global Recovering report is not attributed to this defect.

## Consumer evidence

Core wheel: `dfdfef2edeb9f8db8697e6b850c05a704698e692a3592ed6d9d827887235f816`.
Connector's 52 selected installed preopen/launch/execution cases passed against
the unchanged Connector wheel. The initial Nexus campaign passed 16 authority
and embedded launch-recovery cases but failed four remote publication cases
before the intended fault: capacity assessment returned `STALE_OBSERVATION`.

The disposable Connector helper's injected discovery callback still accepted
no arguments, while the independent inventory observer passes `adapter_ids`
and `cancel_requested`. Its stored observations were `DISCOVERY_FAILED`, and
binding revalidation recorded `observation_failed`. Updated only that native
test adapter to the current signature and filtered its synthetic candidate by
adapter. Production freshness and authorization checks remain intact.

The focused rerun and artifact hashes are recorded in
`m5a-consumers-results.json`. These cross-process tests check reservation/binding
commit-reply loss, replacement connection, lost recovery ACK, no replay of old
work, exact capacity release and successful subsequent handoff.

## Remaining integration

The Connector preparation-failure reproduction still disconnects the whole
control connection. Shared Core refusal alone does not solve this: persist
the association, stop/join the exact producer and renewal, fence original
admission, release only proved matching resources, and deliver the failed
receipt plus canonical session closure without replacing the healthy owner.
Qualify crash/lost-ACK replay and already-admitted conflicts; retain uncertainty
where proof is missing. Exercise equivalent cases in embedded and separate
local Connector processes, then validate the major milestone in the Nexus UI.

No production restart, installation, new provider request or completed M5/UI
gate is claimed by this dependency checkpoint.
