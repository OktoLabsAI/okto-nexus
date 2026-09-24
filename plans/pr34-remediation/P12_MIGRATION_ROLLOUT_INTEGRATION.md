# Migration and active-disable integration

2026-09-24, branch feature/v0.2.0, parent44a1f78. Seven reviewed paths were
transferred from the detached worktree after full Linux70522 terminated.
Pre-transfer main source matched58ca69b; transferred bytes matched the qualified
worktree. No local generated dashboard assets were changed or staged.

The unit adds operator-only historical profile-field diagnostics, preserving
canonical identity and requiring an explicit trusted source for restoration.
It also fixes delayed native fact correlation: current-owner exact acceptance
and terminal facts may resolve a transport OUTCOME_UNKNOWN, without replay.
Session, connection, attempt, epoch, native turn, frozen old-owner recovery and
explicit reconciliation fences remain in force. Schema061/surface56/identity24
are unchanged. Existing additive migrations are tested, not rewritten.

See P03_LEGACY_PROFILE_REVIEW.md and P12_ROLLOUT_BACKLOG.md for behavioral REDs,
intermediate fixture errors, isolated results and limitations. Integration also
extends historical event/session preservation, populated interrupted backfill,
old-unread activation and repeated legacy notification acceptance assertions.

## Integrated validation

Windows44537 completed87 PASS312.55s, exit0, one existing Starlette/httpx warning. Linux81306 completed87 PASS328.66s, exit0, the same deprecation warning. Source hashes and outcomes are in evidence/p12-migration-rollout-integrated.json.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_legacy_profile_review.py tests/test_runtime_endpoints.py tests/test_runtime_attempt_history.py tests/test_runtime_rollout.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_commands.py tests/test_runtime_work_results.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_legacy_profile_review.py tests/test_runtime_endpoints.py tests/test_runtime_attempt_history.py tests/test_runtime_rollout.py tests/test_runtime_result_correlation.py tests/test_runtime_restart.py tests/test_runtime_operation_reconciliation.py tests/test_runtime_commands.py tests/test_runtime_work_results.py
rtk proxy ruff check src/okto_nexus/application/endpoints.py src/okto_nexus/adapters/outbound/sqlite/endpoints_repo.py src/okto_nexus/adapters/outbound/sqlite/runtime_journal_repo.py tests/test_runtime_legacy_profile_review.py tests/test_runtime_endpoints.py tests/test_runtime_attempt_history.py tests/test_runtime_rollout.py
rtk proxy .venv/Scripts/python.exe -m pytest -q plans/pr34-remediation/test_evidence_tools.py
rtk git diff --check
```

Ruff and diff check PASS; evidence tools16 PASS0.17s. Concurrent platform
selections use separate disposable stores. Their durations are not benchmarks.

The CONTRIBUTING live stdio MCP smoke also passed, exit0 and
`LIVE E2E RESULT: PASS`. It exercised actual MCP initialization, coordination,
message/event, handoff and artifact paths without a native model. The launcher
removed ambient app/provider configuration from the child environment and used
temporary homes; no operator credential was passed. Exact PowerShell command:

```powershell
rtk proxy .venv/Scripts/python.exe -X utf8 -c @'
import os,subprocess,sys,tempfile
from pathlib import Path
base=Path(tempfile.mkdtemp(prefix='okto-pr34-live-smoke-'))
env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP'}}
env.update(HOME=str(base),USERPROFILE=str(base),PYTHONPATH=str(Path('src').resolve()),PYTHONIOENCODING='utf-8',OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS='false')
with (base/'result.log').open('w',encoding='utf-8') as log:
    result=subprocess.run([sys.executable,'scripts/live_client.py'],env=env,stdout=log,stderr=subprocess.STDOUT)
text=(base/'result.log').read_text(encoding='utf-8')
print('log='+str(base/'result.log'))
print('exit_code='+str(result.returncode))
print('\n'.join(line for line in text.splitlines() if 'LIVE E2E RESULT:' in line))
if result.returncode: print(text[-2500:])
raise SystemExit(result.returncode)
'@
```

Log: `C:/Users/jpamb/AppData/Local/Temp/okto-pr34-live-smoke-g7k31u8a/result.log`.
This baseline smoke does not replace feature-enabled acceptance or native gates.
No approved native provider campaign was replayed in this unit.

Remaining: retention/deactivation T-MIG-09, outstanding exact matrix stimuli,
crash/load/leak and comparable performance, final current-source regressions,
package/build/install0.2.0. Pi and dedicated attach native remain NOT_RUN.
Final gate NOT PASSED; no merge authorized or performed.

Both integrated gates are terminal. T-MIG-01 through T-MIG-07 scoped acceptance is now PASS for this hashed integration; original58ca69b failures remain historical. No aggregate phase or final gate is promoted. No live test processes remain.
