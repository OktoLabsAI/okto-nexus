# Crash and same-store recovery under bounded CPU pressure

2026-09-24; parentaf53f82 (full source SHA is captured by the campaign). COMPLETE for the bounded fixture campaign; final plan gate remains NOT PASSED.

runtime_recovery_pressure_campaign.py reuses the production HTTP owner and existing exact crash/recovery scenario from test_runtime_relay_process_restart.py. Two owned CPU workers and each actual owner share one allowed CPU, with CPU-time and iteration progress measured over the entire cycle. Each cycle creates an isolated store, crashes its first owner and starts a second owner against that same store. Store is fresh only between cycles. Protocol peers are Python fixtures, never installed providers or ambient accounts.

Alternating cuts cover a terminal fsynced in the journal before projection and a relay child accepted before terminal. The reused scenario asserts causal root/deadline preservation, exact operation identities, publication/idempotence, foreign keys and native write records. The accepted child remains OUTCOME_UNKNOWN without a new wire send; recovery of captured terminal evidence never replays the parent. Both owners stop before recording campaign RSS/descriptors/threads, and owner RSS/descriptors are sampled separately while live.

The campaign sets a600s offset only on the recovered application's injected clock to cross the owner lease boundary; it does not change the host clock, journal durability or authorization. Per-process readiness default remains20s for ordinary tests; a new optional fixture argument lets this explicitly saturated campaign use60s. Two warmup cycles precede measured cycles. Declared resource bounds remain warmup RSS+16MiB, descriptors+8, threads+2. Load workers have a bounded900s safety deadline and explicit finally cleanup.

Initial Windows31566 failed the20s readiness deadline before the first recovery cycle; Ruff initially found2 semicolon style errors, corrected. Windows3488 also failed the60s readiness deadline. Both failures are retained, not PASS. A diagnostic variant adds periodic Python stack dumps; the observed stacks advance through importlib file loading, FastAPI/Starlette and FastMCP imports rather than showing a fixed deadlock. Its first full warmup crash/recovery cycle passed in111.62s with measured load CPU fraction0.885. This observation alone does not qualify the campaign.

The fixture also accepts httpx.ReadError alongside RemoteProtocolError for a lost response at the deliberately crashing owner. The exact owner exit code, persisted state and wire effects are still mandatory; this does not suppress arbitrary application failures.

Historical diagnostic run at document creation: Windows exec43885,4 measured cycles requested (plus2 warmup). Source/tests must remain unchanged while this handle is live. It is not a reason to start another copy. Raw output destination .git/pr34-evidence/recovery-pressure-windows-diagnostic.json. Linux has NOT_RUN for this campaign so far.

```text
rtk proxy .venv/Scripts/python.exe -X utf8 plans/pr34-remediation/runtime_recovery_pressure_campaign.py .git/pr34-evidence/recovery-pressure-windows-diagnostic.json --cycles 4
rtk proxy ruff check plans/pr34-remediation/runtime_recovery_pressure_campaign.py tests/test_runtime_relay_process_restart.py
```

Remaining: terminal campaign result, exact hash/cleanup/resource verification, Linux execution, and original T-E2E-04 mapping. No phase, full matrix, comparable benchmark or final release promotion.


## Final campaign refinement

Diagnostic exec43885 is terminal FAIL. It completed2 warmups plus1 measured journal-terminal cycle, then a later owner exceeded60s readiness while stack dumps showed continued dependency-file imports. The partial sample and diagnostic stack tail are preserved; this is not a passed campaign.

The final loader imports the fixture module and FastMCP before applying the single-core affinity. It then calls the unchanged fixture main/bootstrap under full measured CPU contention. Load workers remain active throughout; all Nexus application startup, authorization, migrations, runtime ownership, traffic, crash, same-store recovery and teardown execute with the owner pinned. Cold interpreter dependency loading is explicitly outside the pinned phase, not silently presented as a cold-start stress pass. No product controls/durability or pressure threshold were weakened.

MeasuredOwner.close now opens exact process witnesses for peer records belonging to the recovered owner before stopping it, then verifies those instances terminated. The journal-terminal recovery must stop one such peer; accepted-child recovery must create none. Existing scenario witnesses cover pre-crash peers. Resource claims therefore include directly observed cleanup on both sides of the recovery.

Final Windows command (run separately from Linux):

```text
rtk proxy .venv/Scripts/python.exe -X utf8 plans/pr34-remediation/runtime_recovery_pressure_campaign.py .git/pr34-evidence/recovery-pressure-windows-final.json --cycles 4
```

Pending final terminal result at this update; no requirement promotion yet.

## Fixture diagnosis and correction

The subsequent Windows worker-exit trial failed after two warmups; stderr was unavailable, so its cause is not inferred. Diagnostic exec76024 captured a load worker PermissionError replacing its JSON snapshot while a reader held it. Its main assertion correctly rejected absent CPU progress; unwinding also raised WinError32 on the fixture SQLite file. Exact task-root process inspection after exit found no surviving fixture commands. No arbitrary process was terminated.

Two standalone real regressions reproduce these resource errors on Windows (2 FAIL, pressure-fixture-red.xml): holding the load snapshot open kills the original worker; disabling cyclic GC and renaming the database after Owner.rows fails because the connection context manager does not close the connection. These are fixture defects, not evidence of product process leakage. Owner.rows now uses contextlib.closing. LOAD retries only PermissionError for at most two seconds and never beyond its overall safety deadline; every other failure remains fatal. The snapshot records cumulative publication retries. This does not retry any Nexus/native operation.

Regression selection:8 PASS Windows66.14s and8 PASS Linux104.28s. Linux verifies execution but its filesystem does not reproduce Windows sharing rules. Ruff PASS. Exact commands:

```text
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pressure_fixture.py -q --junitxml=.git/pr34-evidence/pressure-fixture-red.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_pressure_fixture.py tests/test_runtime_relay_process_restart.py tests/test_runtime_commit_crash.py -q --junitxml=.git/pr34-evidence/pressure-fixture-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_pressure_fixture.py tests/test_runtime_relay_process_restart.py tests/test_runtime_commit_crash.py -q --junitxml=.git/pr34-evidence/pressure-fixture-linux.xml
rtk proxy ruff check tests/test_runtime_pressure_fixture.py tests/test_runtime_relay_process_restart.py plans/pr34-remediation/runtime_crash_pressure_campaign.py plans/pr34-remediation/runtime_recovery_pressure_campaign.py
```

Per-node RED/GREEN manifests preserve outcomes and changed-file hashes. Production code is unchanged. Historical af53f82 crash-pressure PASS applies to that original helper hash, not retroactively to the updated LOAD. Recovery-pressure campaigns qualify the updated helper with the full lifecycle stimulus.

## Final observed result

Windows exec67482 and Linux exec85524 both terminated with exit0 and PASS. Each executed2 warmups plus4 measured cycles, alternating both crash cuts. Each measured campaign witnessed8 owners stop, original peers stop and2 newly spawned recovery peers stop; ambiguous-child recovery spawned no new peer. Both CPU workers exited0 with empty stderr. Campaign/helper/scenario hashes match the recorded files. Resource bounds passed on every measured sample.

{
  "windows": {
    "cycles": 4,
    "warmup": 2,
    "min_cpu_fraction": 0.8148371515139007,
    "maximum_cycle_seconds": 25.793653400003677,
    "growth": {
      "rss_bytes": 1552384,
      "handles_or_fds": 0,
      "python_threads": 0
    }
  },
  "linux": {
    "cycles": 4,
    "warmup": 2,
    "min_cpu_fraction": 0.8130122283180293,
    "maximum_cycle_seconds": 16.613114649000003,
    "growth": {
      "rss_bytes": 118784,
      "handles_or_fds": 0,
      "python_threads": 0
    }
  }
}

Linux command:
```text
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -X utf8 plans/pr34-remediation/runtime_recovery_pressure_campaign.py .git/pr34-evidence/recovery-pressure-linux-final.json --cycles 4
```

T-E2E-04 is PASS only for these bounded synthetic lifecycle samples, combined with the independent six measured exact-owner-kill cycles per platform in P12_CRASH_PRESSURE.md. Not a native-provider leak claim, indefinite endurance qualification or comparative performance result. Pi/attach native gates remain NOT_RUN; no P12/final gate is promoted. Next dependency: comparable benchmark and the remaining assertion-to-evidence gaps.
