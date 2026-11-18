# SI-017 conversation view and exact navigation

Technical activity and Conversation share one session context. Switching views preserves the conversation component, caret selection, draft, and transcript scroll position. The inactive conversation stops reading transcript pages and closes its SSE feed. Authority and existing receipt checks continue separately. The technical event history stays read-only. A new-message announcement is grouped while reading earlier messages, and the keyboard shortcut through the New messages button moves focus to the transcript.

## Evidence

- The frontend suite passed 417 cases. TypeScript, the production bundle, the offline package build, and strict Twine checks passed.
- Headless Edge exercised both views using keyboard controls in one contextual dialog. The conversation stayed hidden and issued no transcript read while five synthetic deltas committed. Returning showed the delta batch and preserved the draft, selection, and scroll. Activating New messages focused the message region.
- The same browser navigated exact links for two sessions on one binding. The sibling did not inherit the first draft or history, and returning restored only the first draft. Navigation created no input. At a 360px viewport, the tested dialog had no horizontal overflow.
- The browser queued one message in the original session and switched to Technical activity. An injected terminal event settled the active synthetic turn, and the server dispatched the queued input to the original session while Conversation stayed hidden. Revoking the fixture login in that view removed protected output and the hidden editor.
- A separate Edge headless run used the browser's actual Page zoom setting at 200% in a disposable profile. The app reported a device pixel ratio of 2 and a 640 by 360 CSS viewport, with visual scale at 1. The exact session dialog fit that viewport without horizontal overflow. Enter and Space switched views, the editor retained its draft and selection, and Enter closed the dialog. The Server recorded zero submitted inputs. The temporary browser and fixture shut down after the check.

## Delivery and rollback

This increment adds no migration. The preceding compatible build can restore the earlier view switching. The queue, journal, Core and Connector pins are unchanged by this view increment. These browser runs used a synthetic Codex peer. Browser keyboard, live-region markup and 200% browser zoom are covered in the tested scenario. Operating-system IME, screen-reader behavior, and native qualification remain pending. SI-017 remains in progress.
