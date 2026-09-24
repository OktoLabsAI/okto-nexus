# P12 — current Linux regression and source review

2026-09-24. Source `58ca69b1afbb04c4272717d8e0028dcb36166e6f` on
feature/v0.2.0. Implementation and tests frozen for this execution; only
documentation/evidence mapping may change meanwhile. Final gate NOT PASSED.

## Linux execution

Execution handle70522 is in progress. Do not restart it because a tool observation
times out or the handle becomes unavailable. Inspect its original JUnit output
and process outcome first; an incomplete run cannot be reported as PASS.

```text
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -c "import os,sys,subprocess,tempfile; from pathlib import Path; env=os.environ.copy(); env.update(OKTO_NEXUS_NATIVE_CAMPAIGN='',OKTO_NEXUS_CODEX_LIVE='0',OKTO_NEXUS_CLAUDE_LIVE='0',OKTO_NEXUS_UI_CAMPAIGN='0'); base=Path(tempfile.mkdtemp(prefix='okto-suite-58ca69b-linux-')); print('suite_source='+subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),flush=True); print('evidence_temp='+str(base),flush=True); raise SystemExit(subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','--junitxml='+str(base/'results.xml')],env=env).returncode)"
```

Printed source matched the SHA above. Original JUnit destination:
`/tmp/okto-suite-58ca69b-linux-0arop3xj/results.xml` in WSL Ubuntu.
No concurrent full Windows suite or real native campaign. Native/browser opt-in
tests are explicitly disabled here and remain separately classified; isolated
fixture processes are allowed. No ambient provider invocation is authorized.

## Reviewed coverage

`evidence/p12-coverage-review-58ca69b.json` currently reviews35 requirements,
including the unchanged prior mapping plus explicit identity/secret corrections
and ten work requirements. Complete and partial coverage remain distinct.
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
