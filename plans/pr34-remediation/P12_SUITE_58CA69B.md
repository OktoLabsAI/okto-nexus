# P12 — current Linux regression and source review

2026-09-24. Source `58ca69b1afbb04c4272717d8e0028dcb36166e6f` on
feature/v0.2.0. Implementation and tests frozen for this execution; only
documentation/evidence mapping may change meanwhile. Final gate NOT PASSED.

## Linux execution

Execution70522 completed exit0:2487 PASS,44 SKIP,2 subtests PASS,2 warnings in2846.46s. Warnings: existing Starlette/httpx deprecation and deliberate Pi death-report callback failure. These are terminal totals, not a per-node manifest.

```text
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -c "import os,sys,subprocess,tempfile; from pathlib import Path; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN='',OKTO_NEXUS_CODEX_LIVE='0',OKTO_NEXUS_CLAUDE_LIVE='0',OKTO_NEXUS_UI_CAMPAIGN='0'); base=Path(tempfile.mkdtemp(prefix='okto-suite-58ca69b-linux-')); print('suite_source='+subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),flush=True); print('evidence_temp='+str(base),flush=True); raise SystemExit(subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','--junitxml='+str(base/'results.xml')],env=env).returncode)"
```

Printed source matched the SHA above. Original JUnit destination:
`/tmp/okto-suite-58ca69b-linux-0arop3xj/results.xml` in WSL Ubuntu.
No concurrent full Windows suite or real native campaign. Native/browser opt-in
tests are explicitly disabled here and remain separately classified; isolated
fixture processes are allowed. No ambient provider invocation is authorized.

## Reviewed coverage

`evidence/p12-coverage-review-58ca69b.json` currently reviews52 requirements,
including the unchanged prior mapping plus explicit identity/secret corrections
ten work requirements, six lifecycle requirements and eleven relay requirements. Complete and partial coverage remain distinct.
Examples of unresolved exact assertions: pool-offer privacy, delayed managed
interrupt completion and combined incompatible-profile/conversation behavior.
These are not promoted from their names or from a green unrelated test.

The review file is not execution evidence. After the suite finishes, generate a
sanitized manifest with summarize_pytest_evidence.py, then join this source review
using build_matrix_evidence.py. Both inputs must carry this exact source SHA.
Retain historical e388227 backend-secret FAIL separately: it describes a defect
fixed at752cd72, not a failure of this subsequent source revision.

Next dependencies: finish mapping all original129 requirements; reproduce/fix
remaining behavior defects or add missing exact acceptance stimuli; complete
crash/load/leak and comparable performance campaigns, migration/rollout checks,
current Windows regression and final build/install0.2.0. Native Pi and dedicated
attach remain NOT_RUN, never converted to PASS from protocol fixtures.

## Terminal evidence limitation and subsequent integration

The JUnit reducer failed with FileNotFoundError after completion: the recorded directory and XML were absent. Scoped inspection of /tmp and /var/tmp found no matching suite XML. Cause is unproven; the suite was not restarted. The terminal summary is preserved in evidence/p12-suite-58ca69b-linux-terminal.json. Do not feed this summary to the matrix builder or infer individual test outcomes from the count. A subsequent final suite must retain and reduce XML in a persistent task directory before its runner exits.

The attempted matrix join also failed because no manifest existed; no matrix output was generated. External observations p12-mig03-observation-58ca69b.json and p12-mig07-observation-58ca69b.json preserve the added behavior REDs independently of the green historical suite.

After the process terminated, seven reviewed migration/rollout paths were transferred from the isolated worktree with byte-hash equality and pre-transfer base-source checks. Integrated validation Windows44537/Linux81306 subsequently passed87 cases each; see P12_MIGRATION_ROLLOUT_INTEGRATION.md. Full58ca69b results do not qualify these later corrections.
