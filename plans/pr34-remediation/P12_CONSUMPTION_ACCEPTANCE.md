# P12 — consumption and socket retry acceptance

Source `96a52e0b9fbb9b536f2d15d295cd3a5ba5578392` plus new test SHA256 `0308335cbf60a7a54b8a7e1b5a821572cfd12ac69f216b6e7ea412418c522939`. Production unchanged. Branch `feature/v0.2.0`.

## Qualified original requirements

- T-CONS-02: owned synthetic Codex emits native acceptance for a held turn. Authenticated worker inbox_pull returns no executable payload while the reserved delivery remains unread/push. Correlated native interrupt terminal then produces one durable result and processing receipt; pull still cannot execute it again. Exactly one native turn starts. HARNESS_ACCEPTED is distinguished from processing completion.
- T-CONS-04: a fixture peer performs its send effect then loses confirmation. Transport becomes OUTCOME_UNKNOWN. Expire its transport lease, run three scans/pulls: same attempt, same unread push reservation, no additional effect or pull payload. The live owner's lease is not replaced or expired artificially.
- T-CONS-06: three explicitly interchangeable approved endpoints; first two attempt actual TCP connects to a reserved, non-listening loopback socket and receive explicit ConnectionRefusedError before any write. The trusted synthetic adapter maps that pre-write proof to RuntimeCommandNotSent. Backoff deadlines advance only the application test clock. Third endpoint receives one effect; outbox attempt_count is3, canonical inbox attempts stays0 and lease remainsNULL throughout. One message delivery/outbox, three audited endpoint attempts. No native deduplication is claimed.
- T-PRES-01: existing production authenticated target grammar cases reread and executed: direct/capability/role/tag/broadcast use canonical presence from harness_open, one full-envelope executor, preserved identity, no manual presence inserts.

## Partial cases retained NOT_RUN in the original matrix

Sixteen create/update × REST/MCP × four-adapter cases prove unsafe mirror_only is rejected before new peers/configuration effects; the original executor remains usable. None of the four adapters currently declares context_without_execution. This qualifies the negative capability boundary, not a positive safe observer transport (T-CONS-07 remains NOT_RUN).

Current journal/result/restart tests also prove rollback, retained fsynced data, checkpoint rewind deduplication, receipt uniqueness and original attempt correlation. They are component evidence for T-CONS-08/T-JRN-03/T-JRN-07; this unit does not promote those rows without their remaining exact crash/duplicate stimuli. The implemented projection/checkpoint share one SQLite transaction; the logical external-checkpoint crash specification must be explicitly mapped when qualifying its full cut, not silently simulated as an extra filesystem checkpoint.

## Commands and observed outcomes

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_consumption_acceptance.py -q --junitxml=.git/pr34-evidence/consumption-acceptance-initial-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_consumption_acceptance.py -q --junitxml=.git/pr34-evidence/consumption-acceptance-initial-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_consumption_acceptance.py::test_two_refused_sockets_do_not_consume_inbox_attempts_or_lease -q --junitxml=.git/pr34-evidence/consumption-socket-initial-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_consumption_acceptance.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_event_journal.py tests/test_harness_target_grammar.py -q --junitxml=.git/pr34-evidence/consumption-acceptance-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_consumption_acceptance.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_event_journal.py tests/test_harness_target_grammar.py -q --junitxml=.git/pr34-evidence/consumption-acceptance-final-linux.xml
rtk proxy ruff check tests/test_runtime_consumption_acceptance.py
rtk git diff --check
```

Initial18 cases: Windows8170 **18 PASS63.99s**, Linux32015 **18 PASS69.86s**. New socket preparation Windows47567 **1 FAIL13.92s**: a1s socket timeout preceded Windows refusal, and the product correctly remained OUTCOME_UNKNOWN. Independent reserved-loopback diagnostic observed ConnectionRefusedError10061 after2.047s. Fixture timeout increased to5s; only explicit refusal is classified NOT_SENT. No product timeout/replay rule changed. A misplaced function insertion was caught by Ruff before execution and corrected; final Ruff PASS.

Final terminal exit0: Windows88660 **49 PASS201.95s**, Linux76818 **49 PASS191.18s**. No failures/skips/warnings in final runs. Exact joins and sanitized node manifests: `evidence/p12-consumption-acceptance-index.json`. Raw XML retained under `.git/pr34-evidence/`; captured logs/credentials are not committed. Earlier transient test generations have no immutable test hash; the final hash is not applied retroactively.

These are selected Nexus fixture gates, not installed-provider or full-suite qualification. No source contract/migration change and no new live MCP smoke requirement. Next: remaining original matrix including pull/push barrier, safe observer, duplicate/capture crash boundaries; then final immutable-source suites and release/build/reinstall. Final gate remains NOT PASSED.
