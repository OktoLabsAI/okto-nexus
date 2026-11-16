# Native question browser qualification

Four focal checks qualify C01 (two native shapes), C02 and E08 against the
installed Nexus0.3.4 wheel `7e156362…`, static bundle `index-D4dmKnLh.js`.
This is the qualified pre-A08 cut. Changes concurrently being prepared for
Server-wide Attention are not attributed to these results.

The fixture reuses canonical opening, lease application, productive admission
and native ingress from `test_native_decisions`. Its remote peer is an in-memory
TestClient WebSocket with actual canonical heartbeat frames. Inventory discovery
is disabled; no native executable, provider call or personal authentication is
used. The TestClient application lifespan has its synthetic host running; the
separate TCP Uvicorn listener has lifespan off. A generated fixture operator key
is used only in this own browser context. The private test-only identity endpoint
must never be installed in a product or personal service.

The server clock and browser Date are fixed consistently to retain the known
canonical lease and question validity during CLI orchestration. Browser timers
run normally. These are not expiry tests; those remain separately qualified.

- C01: Home's Open question resolves the exact canonical request. Native multiple
  options, custom-answer entry and descriptions remain intact. A second fixture
  proves integer/boolean/optional-string inputs, bounds and explicit empty values,
  without adopting schema defaults or making a POST while inspecting.
- E08: two real browser tabs load the same request. The stale tab's actual POST
  is held at a request barrier, the other tab's POST reaches the canonical API
  and returns202, then the held POST continues unchanged and receives409. The
  stale tab renders the canonical reason. No POST response is fabricated.
- C02: Home shows Awaiting agent response and opens that exact session/operation
  with read-only committed input history. It offers no answer/denial controls.
  The operator's input inbox is empty; a direct actual operator attempt returns
  403 and leaves the canonical approval pending.

All final own fixture processes returned0 after normal stop; own browser sessions
were closed. No user tabs, personal profiles, Windows session or provider were
changed. No receipt here claims native application of the recorded decision.

Antecedents are test preparation, not acceptance: absent synthetic heartbeat made
the first peers disconnect; the original observer targeted the unmounted
`/v1/runtime/...` UI URL instead of the actual runtime-management mount; a broad
English regex rejected the old-tab alert without preserving its text. The final
test compares the displayed text to the actual canonical409 reason. Another
attempt caught mixed concurrently edited Home sources and failed with
`KeyError: server_attention`; it was stopped and replaced with the immutable
installed cut. No product fix or PASS is inferred from these antecedents.
