# PR-04 — participant doctor and bounded MCP negotiation

2026-11-06, Windows 11 10.0.26300, Python 3.13.1. Nexus 0.3.3 remains on
`feature/v0.3.3`. Core 0.0.14 and Connector 0.0.12 are unchanged in this
increment. Scope: participant diagnosis in DX-07 and credential-context checks
in DX-04. Full R3 and productive M1/M2 remain incomplete.

## Implemented behavior

`okto-nexus doctor --mode participant` selects the private participant profile
and reports independent levels. Default inspection reads the checkpoint and
owned client entry without vault/environment-secret reads, HTTP, process launch,
configuration repair or checkpoint advancement. Missing profiles create no
directories. File drift remains a separate failure from authentication.

`--check-server` explicitly reads the existing protected credential and verifies
the selected identity/workspace against the pinned Server. Revoked credentials
are refused without repair or rotation. `--check-environment` inspects only the
profile's named reference in this doctor process. Missing/malformed values fail;
there is no silent vault fallback. With Server checking, that exact environment
value is authenticated and labeled `doctor_process`. It does not prove an
external terminal, GUI, shared daemon or harness inherited the value.

`--check-mcp` includes authentication, then uses the existing MCP SDK to
initialize and list tools only. It checks required names/basic input fields for
session, message and handoff entry points, not authority to invoke them or their
productive results. The bounded adapter pins every request to the selected
origin and `/mcp` mount. Only the exact same-origin `/mcp` → `/mcp/` normalization
is allowed; arbitrary redirects, methods/paths and compressed responses are
refused. Limits: 16 requests, four list pages, 512 advertised tools, one MiB per
response stream and an explicit timeout. This check's SDK logging context
suppresses raw remote diagnostics, including session IDs and echoed payloads.

MCP evidence is labeled `participant_doctor`; reload, actual harness credential
delivery, participation, handoff and work remain separate unknown levels. No
tool, agent session, message, handoff, grant or model turn is invoked by the
diagnostic implementation. Successful transport negotiation is not productive
work or proof that a separate external client is ready.

## Evidence

- `pr04-participant-doctor-source.xml`: **32 passed** — 19 participant cases
  and 13 existing managed doctor CLI cases.
- `pr04-participant-doctor-source-initial.xml`: **30 passed, one failed**.
  An already-buffered oversized mock response bypassed the streaming wrapper's
  limit and produced a generic parse failure. Added an early Content-Length/
  buffered-body guard and retained stream-limit refusal even when the SDK wraps
  its exception. Both buffered and streamed oversized cases pass in the final
  32-case source suite. The initial report is preserved.
- `pr04-participant-doctor-installed.xml`: **55 passed** outside the checkout
  against the final wheel: 19 participant doctor, 21 participant init, 13
  managed doctor CLI and two HTTP-only CLI regressions.
- The real TCP case runs the actual Nexus FastAPI/auth/SQLite/MCP composition
  behind a temporary Uvicorn listener. A valid existing fixture key negotiates
  MCP over the socket; files, bindings, runtime/grants and agent-session rows
  remain unchanged. Participation, handoff and work remain unknown despite
  negotiation/surface PASS. No real user key or OS vault was used.
- Negative cases cover missing/invalid environment, revoked credential, changed
  file, redirects, malformed/secret-shaped response data, timeout, oversized
  buffered/streamed responses, compression, tool/page/request budgets and
  incompatible input fields. Captured SDK diagnostics do not expose the
  synthetic credential. No `tools/call` is issued by the mock-wire cases.
- `pr04-participant-doctor-cli.json`: actual installed console entry point,
  absent profile, no directory creation and all effect flags false.
- Ruff E9/F, whitespace and `uv lock --check --find-links vendor/wheels` pass.

Campaign directory:
`C:\Users\jpamb\AppData\Local\Temp\r3-participant-doctor-u3q8_ghs`.
Nexus was built from a fresh source copy. After the response-limit fix, the final
wheel was rebuilt from another fresh copy and installed before the installed
suite. All **444 Python payloads** and **seven static assets** match repository
bytes. Wheel SHA-256:
`a1ff3a68f86d27aab17ca11e17293c606d213905eb74bb399f46025039c8e07f`.
The validation venv uses MCP **1.30.0**, httpx **0.28.1**, anyio **4.16.0** and
the unchanged coordinated Core/Connector wheels. Package details are in
`pr04-participant-doctor-wheel.json`. No release was published.

## Remaining work

DX-04/07 and PR-04 remain in progress. Actual external harness credential
inheritance/launch, client-side MCP behavior, protected-vault qualification,
cooperation smoke, participant cleanup/compensation and full M1/M2 remain
pending. Other platforms and SDK/client versions are not qualified by this
campaign. The SDK check never substitutes for a real harness or productive
request. The fixed original plan is unchanged.
