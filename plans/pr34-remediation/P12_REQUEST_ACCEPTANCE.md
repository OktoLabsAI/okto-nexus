# P12 — concurrent request identity acceptance

Source `f49c82bc10853a358af46f9f5dd7b7f648d6420b` plus new `tests/test_runtime_request_acceptance.py` SHA256 `41bbefd989c2091b393f9e3c531f56bf25d28845f79b51b941e0334a64c09482`. Production unchanged. Branch `feature/v0.2.0`.

T-TX-03: three barrier-controlled pairs (REST/REST, MCP/MCP, REST/MCP) use one authenticated actor and one-use scoped grant. Both requests return the same logical command while its native write is held. SQLite has one command and one grant charge. After releasing the peer there is exactly one native effect; a later retry returns that same operation.

T-TX-04: both surfaces reject key reuse with changed content, target session or expected-owner context. Both target sessions have positive scoped authority, so the target conflict is not an ACL failure. Immutable original admission fields/payload remain identical, its spent grant stays charged once, the second target grant stays unused, and the original key still resolves successfully across the other surface. No second write is issued.

The logical context mapping is the canonical `expected_owner_epoch`; target maps to `session_id`/its endpoint. No generic payload identity gains authority. Existing serial/open/recovery coverage remains in P12_COVERAGE_REVIEW_F12C169.md; its partial classification is historical and superseded for these two rows only by this evidence.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_request_acceptance.py -q --junitxml=.git/pr34-evidence/request-acceptance-initial-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_request_acceptance.py -q --junitxml=.git/pr34-evidence/request-acceptance-initial-linux.xml
rtk proxy ruff check tests/test_runtime_request_acceptance.py
rtk git diff --check
```

Windows73653 terminal exit0: **9 PASS31.59s**. Linux92170 terminal exit0: **9 PASS35.05s**. Ruff PASS. No failures, skips or provider calls. Sanitized per-node manifests and exact node joins are in `evidence/p12-request-acceptance-index.json`. Raw XML remains under `.git/pr34-evidence/`.

These are synthetic native peers through production authenticated HTTP/MCP and real SQLite, not native connector qualification, a new shared contract, or a full-suite gate. No product defect was asserted merely because the prior coverage catalogue was incomplete. Next: remaining original matrix gaps (including socket retry/inbox accounting), final immutable-source suites and release checks. Final gate remains NOT PASSED.
