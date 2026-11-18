# SI-017 exact conversation stream

The dashboard follows an authenticated, exact-session SSE feed of committed cursor changes. The feed publishes the stream epoch, contiguous position, and gap state. The existing bounded transcript endpoint still projects the messages. The browser reads from its current cursor after a change and keeps periodic capability and receipt reads. If the stream is unavailable, it resumes bounded transcript polling. A foreign scope, replaced owner, or revoked login cannot continue the previous stream.

The conversation keeps its rendered message identities and input state during committed updates. A reader above the newest message receives a single New messages control and can choose when to jump. History pagination stays explicit and a queued Load more click survives a snapshot already in flight.

## Evidence

- 99 Python tests passed. The stream tests check unchanged positions, cursor advancement, login revocation before another frame, and bounded termination reasons. The runtime integration verifies that wrong workspace, stale owner generation, and extraneous query fields cannot open the stream.
- 417 frontend tests passed, including the position and owner validation. TypeScript and Vite, focused Ruff, the offline lock check, Git diff checks, and strict archive checks passed.
- Headless Edge connected over SSE to an isolated Uvicorn dashboard with a synthetic Codex peer. The idle view did not reread the transcript. Five new deltas were rendered after one bounded read beginning at the existing cursor. The draft, textarea focus and selection, and earlier transcript scroll position stayed intact. The New messages control jumped to the latest output, and revoking the fixture operator login cleared the panel. This run exercises browser behavior with synthetic data. It does not qualify the native harness, operating-system IME, or screen reader.

## Delivery and rollback

The new endpoint is read-only and adds no migration. Rollback restores bounded periodic transcript reads. The existing queue, receipts, transcript storage, and Core and Connector pins remain compatible. SI-017 remains in progress for cross-session navigation and the remaining keyboard, zoom, pause, and assistive technology checks.
