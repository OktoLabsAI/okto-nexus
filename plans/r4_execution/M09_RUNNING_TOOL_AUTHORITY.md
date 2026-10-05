# Running native tool authority

The Connector now distinguishes qualification of a new runtime from validation
of a native action belonging to an already-running Core session.

Before each runtime composition, the complete executable and Pi dependency
closure are still hashed. A native tool call retains the original execution
selection and rechecks the persisted binding, realization, launch configuration,
secret references, physical workspace/provider-home identities, executable and
entrypoint fingerprints, and exact session selection before and after capability
metadata retrieval. The existing Core bridge checks the current session context
and lease around this work and before the domain request. This path cannot
authorize another launch.

## Observed defect and correction

The retained Pi diagnostic measured capability bridge calls of approximately
26 seconds, with repeated full installation qualification consuming most of that
time. The native ingress deadline remains 10 seconds. Late completion therefore
produced conservative uncertain outcomes even when a domain producer eventually
committed. The correction removes repeated *new runtime qualification* from
running tool metadata checks; it does not extend deadlines, increase buffers,
reuse qualification across launches, or weaken Core lease fencing.

The real-provider campaign now runs the Nexus Server in a separate Python
process from the Connector daemon, using actual HTTP/WSS and public CLI
subprocesses. The Server helper permits the R4 preview only within the test;
native provider qualification remains unchanged. Server and daemon must both
exit normally, and campaign credentials must be removed.

The prior native event-observation failure has no captured concrete exception
yet. A subsequent successful journey demonstrates this tested configuration,
not a general proof that every event-loss cause has been corrected.

## Verification

- 60 directed source cases passed, including drift before and after metadata.
- 263 installed Connector regression cases passed.
- The initial two new assertions incorrectly matched a CoreError code against
  its human message. Their failed XML is retained; assertions now inspect code.
- The real installed Pi journey passed with three native actions, a completed
  handoff, successful turn/close receipts, renewed lease, and normal cleanup.

See the coordinated running-launch evidence index for the final provider
results, artifacts, commands and limitations. No milestone or release gate is
closed by this increment.
