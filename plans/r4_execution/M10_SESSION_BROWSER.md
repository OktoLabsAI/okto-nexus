# Canonical session browser — 2026-10-02

The selected connection now offers a Previous sessions table with lifecycle,
lease and read-only event history, including closed sessions. This uses the new
GET `/v1/runtime/sessions` endpoint, requiring executor, binding and subject IDs.
The authenticated subject, recorded opening actor or current verified operator
can read the corresponding history. Foreign scopes return an empty list.
The endpoint authenticates and projects individual SessionViews within one read
transaction; it neither grants authority nor creates operations.

Pagination uses ascending session ID and an exclusive after_session_id cursor,
with a 1–100 API limit (25 in the UI). Refresh starts at the first page, so newly
created IDs below a previously visited cursor are found on refresh. Unknown or
duplicate query fields are rejected. Responses are no-store. The UI validates
Server/agent/executor/binding, ordering and cursor before displaying results.
Changing the selected session unmounts the prior event reader. Process state
remains UNKNOWN; CLOSED does not prove native process death.

## Evidence

`evidence/session-list-installed/`: eight passes in 41.33 s, Windows/Python
3.13.1 and headless Edge, PASS/exit 0/changed_inputs=[]. This covers paginated
closed-session reads, schema conformance, subject/operator/foreign visibility,
invalid/duplicate queries, existing session expiry/disconnection/collision cases,
two-session browser navigation without new POST/native openings and NS15.05.
`evidence/session-list-visual/`: one supplemental browser pass in 11.29 s, same
wheel and unchanged inputs, capturing the visually reviewed table and history
in `evidence/session-list-screenshots/closed-session-browser.png`.
Native peers are synthetic; HTTP handlers, authorization, persistence and browser
assets are from the installed package.

Wheel SHA-256: `bdcaa07b84f826a6b87d055b8eddc2daad14472c264a5269f3aea79381878d61`.
Sdist: `3aecb634b523fd4e9327e27cf0aeeea4439edf92d3cbf800c16d058ce11f3b06`.
The isolated build freshly compiled TypeScript/Vite and preserved the user's
static assets. Core .56 and Connector dependency wheel hashes remain
`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6` and
`93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

The contract catalogue, SessionListView schema and milestone mapping include the
new route. The first document validator run rejected the old fixed count of 26;
updating that count to 27 restored PASS_DOCUMENT_COVERAGE_ONLY. This validates
mapping coverage, not product acceptance. Reproduction uses the installed runner,
wheel and test selection in the campaign JSON, with OKTO_NEXUS_UI_CAMPAIGN=1 and
OKTO_NEXUS_UI_INSTALLED=1 for browser cases.

## Remaining scope

This browser is reached through a selected inventory-backed connection. A global
archive independent of current installation selection, old stream-epoch selection,
uncertain-session repair and complete operator recovery journeys remain open.
No actual provider/remote browser, native Mac, independent-host, final clean
installation or G0–G3 acceptance is inferred. Earlier real Pi evidence used the
preceding UI wheel and remains separately scoped. Hosted CI remains deferred.
