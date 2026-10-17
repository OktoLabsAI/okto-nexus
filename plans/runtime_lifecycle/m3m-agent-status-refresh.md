# M3m — Agent status refresh after returning to the browser tab

On 2026-10-17 the operator reported that every local runtime agent was shown as Recovering. Read-only inspection of the running server at `127.0.0.1:8202` found generation 73 `CONTROL_READY`, a current dispatcher heartbeat, and Pi, Claude, and Codex in `READY`. The same `/api/v1/agents` endpoint used by the UI returned `Ready` and `present` for all three. No recovery event followed Pi's automatic recovery at 10:34:29 UTC. The operator confirmed that reloading the Agents tab displayed all three as Online. No server or agent process was restarted.

The frontend's ten-second agent poll intentionally skips hidden documents. It had no immediate refresh on visibility/focus, leaving a previous Recovering observation visible until another poll or reload. M3m refreshes immediately when the tab becomes visible or focused and queues one follow-up request if a poll is already in flight. The change does not alter runtime reconciliation or claim that tab visibility caused the original observation; that attribution remains open in L12.

Validation: TypeScript and production frontend build, plus `git diff --check`. Live UI verification of this new bundle is pending a controlled rollout; the running global installation remains unchanged.
