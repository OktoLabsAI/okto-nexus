# L17: real UI reset with preserved runtime configuration

2026-10-17, Windows native, installed final M3k notification candidate.
This is a disposable Pi qualification, not the complete UI-A/provider matrix.

## Isolation and artifact

The test used `http://localhost:8204/`, agent `m3k-pi`, and the home/workspace
under `build/runtime-m3k-real-ui`. Before reset, the stopped disposable home was
copied to `build/runtime-m3k-ui-before-reset` and all 13 copied files were hash
verified. Production home, history, server PID 32480 and port 8202 were untouched.

The wheel SHA-256 is
`dc0d8130ec7ac33fb368e0c035c4a85dc1cef4d519c2e45b44a524348cd7c5db`.
The fixture resumed through the normal installed CLI/lifespan as server PID
31352. All reset and message actions were performed through the Nexus UI.

## Idle reset

Settings > Storage > Reset used the checked preserve-agents option. The UI
showed Working, then Reconnecting agents, and only then completed. Generation
6 drained at 09:19:13.314 UTC; generation 7 had its pump at 09:19:14.974. No
manual reload, installation review or agent reconfiguration was needed.

A new Meta-harness message returned `M3K_RESET_OK` with 1/1 ACK at 09:21 UTC.
The workspace and destination were available automatically.

## Reset during execution

The first 90-second sleep finished before reset while an unrelated production
status report was investigated. It is not counted as an interrupted execution.

A second controlled message, subject `M3k active reset qualification`, was sent
at 09:27:28 UTC. The real terminal showed a running `bash` call (`sleep 90`),
started at 09:27:36, in session `ses_37c91b1c43b0404880b7656999ebade8`.
Reset was requested through the same preserve-agents UI before the sleep could
complete: generation 7 entered draining at 09:29:02.857, drained at
09:29:04.335, and generation 8 had its pump at 09:29:05.815. HTTP PID 31352
remained unchanged. The reset result reported two completed results for the
three pre-reset turns, one delivery release and one release notification;
the interrupted turn was not manufactured into a successful native result.

After the reset reported `pending=false`, a new Meta-harness message was sent
without changing settings or resending failed delivery. It opened session
`ses_f16f20c71780240f91cc21df584ea2b7`; turn
`op_b8d5762f11320c3aaab0d93d89df4480` returned `M3K_RESET_ACTIVE_OK`, visible
with 1/1 ACK. Agents displayed Local Online. This establishes new-work delivery
after reset; it is not a cold-start latency benchmark.

## Preservation and evidence limits

Five populated configuration tables remained byte-for-byte equivalent at row
level: execution bindings, local realizations, workspace bindings, endpoints
and runtime profiles. Agent API-key equality was checked without printing keys.
The workspace differed only in `last_seen_at`. Six other configuration tables
were empty on both sides; this does not qualify real MCP preset preservation.
The foreign-key check was clean.

Private local evidence: fixture `evidence.jsonl`, `observations.jsonl`,
`reset-comparison.json`, stopped pre-reset backup and its manifest. Browser
snapshots and screenshot output confirmed the real UI results; no persistent
screenshot artifact is claimed. The frozen-input installed campaign is recorded
separately in the milestone ledger when it finishes.

The fixture drained normally at 09:32:07.055 UTC with no remaining resources or
error codes and finished its lifespan at 09:32:08.187. PID 31352 and the 8204
listener were absent afterwards.
