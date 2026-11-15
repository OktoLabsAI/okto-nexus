# HOME-R1 semantic boundaries and result titles

Source qualification only. The tests use synthetic SQLite stores and existing
application/HTTP fixtures; no provider, live service, native runtime or OS event
was executed.

The initial run retained in `before.xml` has 7 passing cases and one failure:
a handoff result displayed the generic “Handoff result” despite having a task
title. The narrow query change reads `tasks.title` through the handoff and its
workspace, limits it to 160 characters, and uses the existing safe projection.
Missing titles retain the existing fallback. Task descriptions are not read.
Both native results and manually completed handoffs now use this title.

`final.xml` records 9 passing cases. The final run adds explicit native/manual
parameterization to the title test; it is not a repeat of nine initial cases.
`result-regressions.xml` records five separate passing existing PR01 tests.

The new tests cover two sessions of the same agent with different execution
states; informational unread broadcast not becoming work; successful turns
not completing or verifying handoffs; native and external activity remaining
separate; canonical refusal of an external instance without a workspace;
omission of synthetic credential, prompt, tool-argument and private-path
markers; and canonical result titles without task descriptions.

A08 remains **NOT_RUN in this qualification**: the current canonical producers
do not supply a genuine server-wide Attention occurrence without a workspace.
No impossible database row or unrelated identity error substitutes for that
requirement. G05 proves refusal at canonical instance registration and no
inferred project activity; it does not invent invalid persisted history.

The earlier package qualification remains bound to its original inputs. This
delta is not an installed-wheel or performance qualification, and does not
change the previously recorded unmet performance target. Root owns acceptance
and ledger updates.

## Subsequent empty-installation correction

Root's real browser review found that the reserved human `operator` identity
made an empty installation appear to have one worker. `operator-before.xml`
retains that failure against the already title-corrected source. The Home-only
agents relation now excludes that identity before totals, revisions and cursor
pagination are computed. The global agents list and Graph are unchanged.
`operator-final.xml` covers the real bootstrap/ASGI empty-to-one-worker flow,
the complete five-worker fixture pagination, and direct-recipient membership.
`operator-qualification.json` pins this subsequent source. The original title
qualification remains an antecedent with its original source and test pins.

## Subsequent presentation redaction correction

Root reproduced a manual handoff result containing a synthetic `nxs_` token.
Upstream native redaction did not cover this path. Home now reuses the existing
pure `harness/event_journal.redact` policy for work/result titles (including
message subjects), result previews and artifact filenames. Text limits are
applied after replacement as well. Opaque identifiers and references are not
rewritten. No credentials, files or runtime state are read by the redactor.

`redaction-before.xml` preserves the genuine title leak and an independent test
fixture collision. `redaction-final.xml` is an intermediate run with four passes
and a second fixture collision; despite its filename it is not a successful
final qualification. `redaction-fixture-final.xml` preserves the missing
canonical result foreign-key fixture failure. Those fixture corrections create
distinct message/delivery identities and the required durable result before
attaching its artifact. `redaction-confirmed.xml` is the final qualification.

This proves only the existing credential-text patterns (`nxs_`, `nxsept_`,
supported `sk-` and Bearer forms) in the bounded presentation fields. It is not
a universal secret, PII or arbitrary private-path detector. Synthetic tokens
in failure assertions are test data, not credentials.
