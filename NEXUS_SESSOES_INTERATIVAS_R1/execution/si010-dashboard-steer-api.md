# SI-010 and SI-014 dashboard API for exact-turn reorientation

An authenticated browser can review an active Codex turn, its same-turn effect, and the queue revision. The server derives two revisions from the committed start proof and the installed Core control contract. Both admission and the R4 send cut recheck the target and effect. A paused queue or unresolved interrupt blocks reorientation. The input uses the original human login and the existing session grant.

Direct reorientation admits a fresh text intent and links it to the control in one writer. A denied or rolled-back attempt leaves the FIFO untouched. Promotion atomically links an owned queued input after checking the input and queue revisions. It keeps the original input ID and removes its eligibility for next-turn dispatch. A separate review can show the original login up to 200 characters of its queued text. Queue listing remains metadata only.

The receipt endpoint supports lookup by original client intent or owned input ID. A replay recovers the existing linked operation. A submitted steer is visible as submitted with consumption still unconfirmed. Migration 178 adds a view so a submitted or definitively refused steer stops occupying ordinary FIFO capacity. A retained uncertain delivery stays visible in the pending queue for reconciliation. The active turn still governs the next productive dispatch.

## Evidence

- The combined runtime, dispatch, containment, interaction and migration run passed 125 Python cases.
- The HTTP integration with a synthetic Codex peer exercises direct reorientation and promotion to the same native target, matching and stale revisions, plain-text gating, foreign origin, another login, bounded own-input preview, and idempotent receipt recovery. Both control payloads reached the exact target once. The ordinary queued message dispatched after the original turn settled. A late attempt against that ended turn left no input receipt.
- The migration regression preserves the seeded schema 176 inputs, controls and queue pause through schema 178. Only the pending view is added by 178. Dependency locking passed offline. The 0.3.8 wheel and source archive passed Twine's strict check. Five packaged entries matched their source bytes, including migration 178 and the dashboard API. The temporary wheel has SHA-256 `d7ea94f2f56085738590c55fbf380a735bd6dc68fee17117bf42f2066b52f9a1`.

## Delivery and rollback

The reorientation endpoints use the existing opt-in interaction gate. This increment covers the Codex exact native target. Pi's observed run and boundary timing, Claude's compound effect, the conversation and queue controls in the browser, and native qualification remain open. Once schema 178 is applied, rollback needs compatible readers for the view and existing durable inputs.
