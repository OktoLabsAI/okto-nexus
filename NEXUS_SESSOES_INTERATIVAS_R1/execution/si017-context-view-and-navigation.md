# SI-017 conversation view and exact navigation

Technical activity and Conversation share one session context. Switching views preserves the conversation component, caret selection, draft, and transcript scroll position. The inactive conversation stops reading transcript pages and closes its SSE feed. Authority and existing receipt checks continue separately. The technical event history stays read-only. A new-message announcement is grouped while reading earlier messages, and the keyboard shortcut through the New messages button moves focus to the transcript.

## Evidence

- The frontend suite passed 417 cases. TypeScript, the production bundle, the offline package build, and strict Twine checks passed.
- Headless Edge exercised both views using keyboard controls in one contextual dialog. The conversation stayed hidden and issued no transcript read while five synthetic deltas committed. Returning showed the delta batch and preserved the draft, selection, and scroll. Activating New messages focused the message region.
- The same browser navigated exact links for two sessions on one binding. The sibling did not inherit the first draft or history, and returning restored only the first draft. Navigation created no input. At a 360px viewport, the tested dialog had no horizontal overflow.
- The browser queued one message in the original session and switched to Technical activity. An injected terminal event settled the active synthetic turn, and the server dispatched the queued input to the original session while Conversation stayed hidden. Revoking the fixture login in that view removed protected output and the hidden editor.

## Delivery and rollback

This increment adds no migration. The preceding compatible build can restore the earlier view switching. The queue, journal, Core and Connector pins are unchanged. These runs used a synthetic Codex peer. Browser keyboard and live-region markup are covered, with operating-system IME, 200% browser zoom, screen-reader behavior, and native qualification still pending. SI-017 remains in progress.
