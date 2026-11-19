# SI-035 Codex work across an interrupted ownership transfer

Three isolated Windows processes ran the installed Nexus candidate, embedded
dispatcher, broker and persistent SQLite database with the pinned Core wheel.
They used the real Codex 0.157.0 app-server and a deterministic Responses
peer on loopback. The package and executable hashes, process outcomes and
native call counts are recorded in the [transfer evidence](si035-codex-productive-transfer.json).

1. The source opened one native thread and submitted one turn through the
   canonical Nexus work path. Nexus returned the exact result and persisted
   a verified saved context. Canonical close stopped the original app-server
   before the next Nexus process started.
2. The next process requested saved resume for the exact source via the
   terminal command's application path. After an injected transient
   inventory race and retry, the test recorded the successor reservation
   and ended the isolated Nexus process with exit code 86 before the
   native send. No app-server call or model request occurred in that phase.
3. The recovered dispatcher fenced the old generation, preserved the original
   retirement witness and used the same admitted operation and successor
   session. Repeating the resume request returned the same identifiers.
   A send to the retired source was refused. The successor sent a single
   `thread/resume` for the original native thread and a single `turn/start`
   for the explicitly admitted next turn. The loopback peer observed the first
   user message in the successor request. The successor returned the exact
   response and closed through the canonical control.

Exactly two model requests reached the loopback peer, one per app-server.
The installed dispatch, saved-context and CLI regressions passed 48 tests.
Earlier fixture evidence separately covers uncertain sends after the send
boundary and the refusal to replay them. This increment extends the
pre-send recovery proof with completed native turns. A real-provider campaign
and full SI-T-G15 qualification remain pending. [Earlier restart results](si023-codex-saved-resume.md)

The increment adds evidence without a product or schema change. Reverting the
evidence commit removes the ledger entries and reports.
