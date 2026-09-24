# P12 — runtime audience and private policy

Parent `5f0e55342d078ccfb1dc92c6183488f516032ba4` plus new test hash in `evidence/p12-audience-privacy-index.json`; production unchanged.

T-PRES-04: each of inbound/outbound is configured through authenticated operator tag/agent REST APIs. An authenticated MCP message excluded by the sender outbound or recipient inbound is rejected opaquely, with no canonical message, outbox intent or native turn. Its error does not expose the private selector/value. A positive allowed message reaches the actual owned synthetic Codex protocol process. Before publication authorization, a barrier outside the writer transaction changes the reverse audience (worker outbound or caller inbound) through REST. The canonical result publisher blocks publication but preserves the captured output. The peer receives only canonical bootstrap/envelope data: private selectors, excluded values and comm_scope are absent from both the sent envelope and echoed native output. Exactly one native turn and original operation remain; no Runtime result message is published.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_audience_privacy.py -q --junitxml=.git/pr34-evidence/audience-privacy-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_audience_privacy.py -q --junitxml=.git/pr34-evidence/audience-privacy-linux.xml
rtk proxy ruff check tests/test_runtime_audience_privacy.py
rtk git diff --check
```

Terminal exit0: Windows40644 **2 PASS33.84s**, Linux28432 **2 PASS35.19s**, no failures/skips. Ruff PASS. Sanitized per-node manifests in index; raw XML under .git/pr34-evidence. No provider calls. This qualifies directed delivery/result projection, not a new complete audit of every core audience expression.

Original matrix120 PASS/9 NOT_RUN. Final gate NOT PASSED; remaining cases, final immutable-source suites, findings/release audit and reinstall0.2.0 still required. Native Pi/attach remain NOT_RUN.
