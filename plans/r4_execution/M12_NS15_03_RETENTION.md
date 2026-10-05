# NS15.03 capture retention and subscriber parity — October 1, 2026

The normative retention rule is ACK eligibility and explicit gaps, not a new
Server history expiration policy (NS10.05). The installed integration now proves
the existing Core/Server behavior through a real canonical domain result:

- Hold Server ingress before its commit while Core has captured terminal output.
  Core `compact_acked` removes zero rows and Server has no result projection.
- Release ingress, wait for governed publication and compact the acknowledged
  Core event body. A cursor preceding compaction raises `EVENT_GAP` explicitly.
- Close the canonical session and run the existing Server retention service
  with a cutoff 400 days later. Canonical event ingress, output, receipts,
  domain result and delivery references remain byte-for-byte unchanged. The
  published message remains readable, foreign keys are valid, and authorized
  operation history still returns the same output.

This preserves the established distinction: Core owns physical event replay
compaction; Server retains committed domain history and provenance. It does not
introduce automatic deletion of referenced results or claim bounded total
Server database size. The per-operation captured output limit remains 1 MiB.
Existing gap/replay and transactional rollback tests run in the same installed
campaign. The retention cutoff is injected only into the retention service;
live owner/lease clocks remain unchanged.

Subscriber audit: production code has no registration with
`HarnessSupervisor.subscribers`. The legacy ingress callback
`publish_projected_event` publishes to that registry but has no production
consumer to migrate. Its compatibility-only notable-message broadcast is not
used by journal-backed production capture. Domain result publication and public
event replay already use canonical projections. Inbox notifications are a
separate domain facility. No additional native event broadcast is introduced.

Evidence: `run_ns15_03_retention.py` and
`test_runs_20261001_ns15_03_retention.json`, using the current installed recovery
wheel. Native peers/readiness remain fixture-qualified. Cross-protocol fallback,
native loader removal, full restore and final provider/platform/release acceptance
remain pending. This increment does not close NS15.03 or the release gates.
