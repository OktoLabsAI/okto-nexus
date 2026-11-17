# Initial source supplement — retained NOT_GREEN

The first cut executed seven cases: **6 PASS / 1 FAIL**. Its original
qualification JSON, raw diagnostic hashes and own Temp data are preserved.
No installed supplement ran. Source/payload/helper guards show no drift;
processes exited normally without timeout, force or observed survivors.

The failing E16 assertion sequence did not reach preference/retention reads:
fixture setup violated the unique canonical-operation key on `runtime_results`
while inserting its second artifact link. Migration 096 permits one canonical
runtime result per operation. Existing grouped-artifact tests use distinct
operations/captures associated with the same logical handoff/claim. This is a
fixture construction error, not a demonstrated product failure. Any corrected
cut must preserve all three artifacts and off-page/seen/no-ACK/retention checks,
not weaken them to one artifact.

The six passing cases have narrower layers than complete ledger scenarios:

- A06 proves the real SQLite v2 reader preserves complete positive sibling keys
  despite the visual source filter. Its historical started-event inputs are
  synthetic. It neither creates a lease nor proves live Working presentation.
- E08/E09 prove actual ASGI/SQLite partial-output projection for unsuccessful
  historical terminal receipts. No real native failure/cancellation or browser
  output inspection is claimed.
- H02 proves actual exact-target denial responses omit the protected preview and
  counter fields. It does not qualify adversarial browser navigation.
- H03 proves API minimization/JSON control encoding, not DOM/ANSI execution
  safety. Public hostile text is permitted as data and needs browser escaping.
- H07 uses an existing canonical native input request and real HTTP stale-action
  denial/history reads. **Revocation is a direct SQL negative-fixture UPDATE, not
  a canonical revocation action or real native lifecycle event.** A genuinely
  created same-name successor/browser continuation is still unqualified.

No scenario status is promoted by these six test passes.
