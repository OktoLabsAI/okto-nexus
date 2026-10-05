# NS15.03 approved canonical boot — October 1, 2026

The existing operator boot configuration and `serve` startup now open approved
canonical endpoints through durable R4 admission and Core dispatch. Startup runs
after embedded inventory and dispatch composition are ready. Stable owner/endpoint
keys replay the same operation; an existing nonterminal session requires
reconciliation before another boot opening can be admitted.

Additive schema 093 stores the boot approval revision and owner identity/epoch on
the opening operation. Admission, dispatch and initial lease authorization check
the current approval, endpoint/profile revisions, approving operator credential
and live owner. The host retains its `runtime_boot` authentication source. Normal
canonical execution grants remain necessary; boot does not mint agent credentials
or confer general control authority. Disabling boot after a ready session does not
revoke that session's separately granted execution authority.

Directed tests exercise actual `serve` startup, stable replay, canonical close,
approval disable/revision/issuer changes between admission and dispatch, a wrong
owner epoch and an existing canonical session. Upgrade tests reconstruct schemas
091 and 092 with historical R4 operations and receipts, apply migrations repeatedly
and check preserved history and foreign keys. The installed campaign includes
admission, dispatch, embedded execution and affected legacy boot/grant regressions.
Commands, hashes and results are in [the manifest](test_runs_20261001_ns15_03_boot.json).

Native peers and readiness qualification remain fixture-local. Remote boot and
real provider/OS acceptance are not established by this increment. Delivery,
event projection and removal of duplicated native loaders/codecs remain pending.
NS15.03 is partial; normative TR4-15-03, M12 and all release gates remain open.

The next caller boundary is `RuntimeDeliveryPlanner` and the delivery callback
in `harness.build_dispatcher`: both still use the legacy registry/session path.
Their conversion must preserve transactional inbox/outbox reservation, sender
authority, recipient scope, exclusive consumption, causality and managed handoff
validation. Canonical admission alone cannot mark a delivery as completed;
durable receipts and result/event projection must retain that distinction.
