# EV-UAT-07 — can an operator complete a first attach by reading `docs/`, without source?

Captured: 2026-09-20, 18:26 -03.

**Verdict: FAILED as literally worded ("reads docs/ ... completes a first attach WITHOUT reading
source code"). No file under `docs/` — or anywhere else an operator would naturally look
(`README.md`, `CHANGELOG.md`) — documents the harness-integrations feature at all.** This is a
real, honest documentation gap, logged as the task instructs, not a case quietly marked passed.

## What was checked

```
$ grep -rln "harness" docs/ README.md CHANGELOG.md
docs/design/0002-design-review-hardening.md          (unrelated hit)
docs/design/0003-analise-indice-recuperacao...md      (unrelated hit)
docs/harness-integrations/research/pi-rpc-protocol-reference.md   (internal research note)
docs/design/0004-harness-integrations.md              (the ADR itself)
README.md                                              (all hits are the PRE-EXISTING,
                                                         unrelated "Meta-harness" dashboard
                                                         chat feature - a different feature
                                                         that predates this work and shares
                                                         only the word "harness")
CHANGELOG.md                                           (same - all "Meta-harness" hits)
```

Zero mentions of `harness_open`, `harness_send`, `harness_list`, `/api/v1/harness/sessions`, or
any of the eight harness MCP tools anywhere in `README.md`, `CHANGELOG.md`, or `docs/` outside:

- the ADR (`docs/design/0004-harness-integrations.md`) — a DECISION RECORD explaining *why*
  choices were made, written for engineers evaluating the design, not an operator's how-to;
- `docs/harness-integrations/research/pi-rpc-protocol-reference.md` — an internal protocol
  reverse-engineering note, same audience;
- `plans/harness-integrations/01-test-plan.md` — a test plan for the dev team, not user docs;
- the `docs/harness-integrations/evidence/` files themselves (including this one) — proof
  artifacts, not documentation, and didn't exist before Phase 4.

None of these is "documentation an operator reads to complete a first attach." There is no
quickstart, no worked `curl`/MCP example, no parameter-shape table for `harness_open`, nothing.

## The fairest version of the test, run anyway

Per this task's own instruction to test the fair version, not just declare failure from a grep:
could an operator get a first attach from `docs/` + `GET /api/v1/harness/kinds` (a live,
non-source, self-describing endpoint) + the MCP tool descriptions (a legitimate non-source-code
surface — these are the exact strings a real MCP client like Claude Desktop or Claude Code's own
`/mcp` integration renders in its tool picker, not something requiring a source read in normal
operation)?

**That combination gets further than expected — and then runs out at one identifiable, sharp
edge:**

- `GET /api/v1/harness/kinds` (real output, captured in EV-SYS-002 and reproduced live in this
  run) enumerates all four kind/substrate combinations and their capabilities
  (`send_only`, `steer_timing`, `multiplexes_sessions`, ...) — enough to know WHAT exists.
- The MCP tool descriptions (read from source here only to quote them verbatim, but they are the
  exact live tool-schema text, not implementation detail) are unusually thorough for parameters:
  `_P_KIND` lists the three valid `kind` values; `_P_SUBSTRATE` explains `stream` vs `attach` and
  when `target_pid` is required; `_P_PAYLOAD_TURN` explicitly warns the payload shape is
  HARNESS-NATIVE and non-uniform (`{"text":...}` for pi/codex, `{"content":...}` for both
  claude_code substrates) — exactly the detail that would otherwise force a source read. An
  operator using ONLY these descriptions could plausibly construct every one of the six real
  `harness_open`/`harness_send` calls this evidence run actually made.
- **Where it runs out, concretely:** `_P_HARNESS_AGENT_ID`'s own description states "other agents
  then address it via the normal target grammar (direct/capability/role/tag)" — a claim EV-UAT-05
  (this same run) and EV-SYS-003 both EMPIRICALLY FALSIFIED for the input direction. An operator
  who trusts the tool's own documentation and tries to reach a harness via `message_create`, as
  the description tells them to, will silently get a `delivered_count: 1` success response that
  never reaches the harness — the single most misleading possible outcome, because the API
  itself claims success. This is not merely an absence of docs; it is a documented, false claim
  inside the one place documentation exists.
- Nothing anywhere — tool descriptions, `/info`, `/harness/kinds`, or `docs/` — mentions the
  composition-root gap already reported in `EV-SYS-002-boot-and-registration.md`: a bare
  `kind="pi"` open with zero extra configuration silently inherits `~/.pi/agent/settings.json`'s
  own default provider. On THIS machine that default is `local-mac`, which resolves to
  `192.168.31.222` — a host this very task was told never to touch. An operator following only the
  public surface, with no knowledge of that file or that default, would have no way to know their
  first `pi` attach just left the machine's default routing untouched and sent a real prompt
  wherever that default points, on THEIR machine, whatever host that happens to be. That is the
  strongest form of this finding: it is not just "the docs are missing," it is "the
  documented-by-absence default path is a silent, unannounced live-inference dispatch to
  whatever host the operator's local `pi`/`codex` config already points at" — which is exactly
  the failure mode `192.168.31.222` being off-limits was chosen, in this task, to make visible.
- Nothing documents the cc-socks receive-side approval gate found in EV-UAT-04
  (`crossSessionInbound`) — an operator following only the public API would see their `send` come
  back `200` and reasonably, wrongly, conclude delivery succeeded.

## Recommendation (finding, not fixed — out of a test-writing task's scope)

A short `docs/harness-integrations/` operator guide covering: the four kind/substrate
combinations and their payload shapes (the tool descriptions already have the raw material for
this); the `harness_open`→`harness_send`→poll-or-subscribe-`harness_event_list`→`harness_close`
lifecycle as a worked example; an explicit correction of the misleading target-grammar claim in
`_P_HARNESS_AGENT_ID`'s own text (input vs. output asymmetry, per EV-UAT-05); and a loud warning
about the backend-selection gap (EV-SYS-002) before anyone runs `kind="pi"` against their own
machine's default provider.

## Verdict

**FAILED**, honestly, as the plan itself invites ("If the documentation does not currently support
that, SAY SO — that is a real finding, and the honest outcome is a documentation gap logged, not
a case quietly marked passed."). The fair, generous version of the test (kinds endpoint + live MCP
tool schema, no `docs/` needed) gets an operator most of the way there, but contains one materially
false claim and omits the one gap this whole task's own safety rules exist because of.
