# Repeated owner death under measured scheduler pressure

2026-09-24, feature/v0.2.0, parentbf5636c05a3d50eb0e7bda8fdeb21d7b474de767 plus new campaign hash. Production and existing ServeFixture unchanged.

runtime_crash_pressure_campaign.py starts the actual serve CLI with explicit integration ON, disposable credentials/home/project, an approved Pi endpoint and an owned Python RPC peer with a sleeping descendant. The fixture ignores EOF, so a pipe closing cannot masquerade as ownership cleanup. Linux additionally witnesses the guardian. This is a synthetic protocol campaign, not a native Pi qualification.

Two bounded CPU workers and the actual serve owner are pinned to the same allowed CPU inside those owned processes only. The campaign verifies the owner's real affinity and both workers' iteration/CPU-time progress in every measurement window; at least25% of that CPU must be consumed by the load. Load starts after protocol readiness and remains active through abrupt owner death and descendant-stop observation. No host-wide affinity/priority changes, remote endpoints or provider calls occur.

The actual owner records its identity from inside the serve launcher. Before termination the campaign holds a Windows process handle with terminate/synchronize rights or a Linux pidfd. It kills that exact instance (TerminateProcess/SIGKILL), waits for the launcher, and observes existing exact peer/descendant/guardian witnesses. The field exact_tree_reaps counts those observed terminated process instances, excluding the separately terminated owner; it is not a scan of numeric PIDs or an exactly-once execution guarantee.

Each platform has2 warmup plus6 measured cycles. Per-cycle evidence records load CPU/wall/iterations, shutdown-to-tree-stop duration, owner RSS/descriptors before death and campaign RSS/descriptors/Python threads after cleanup. Bounds declared before results are warmup RSS+16MiB, descriptors+8, threads+2. Load workers have a300s safety deadline and are explicitly stopped/reaped in finally. No native traffic is replayed.

## Campaign development observations

- Initial Windows41199 failed before readiness when CPU pressure also covered heavy startup/imports and exceeded ServeFixture's20s readiness deadline. Temporary logs were not retained by that initial version. This run did not qualify pressure cleanup and is not counted as PASS. The required kill-under-load stimulus was isolated by activating load only after readiness; startup-under-pressure remains outside this campaign.
- The next two Windows attempts failed the newly added exact affinity assertion: the Popen launcher reported all16 CPUs while the code executing PIN selectedCPU0. Both failures are retained in p12-crash-pressure-windows.json and p12-crash-pressure-windows-check.json. They concern the measurement/termination target, not a proven product ownership defect. The campaign now records the actual serve PID internally and holds its exact handle/pidfd before measurement/kill.
- A task-scoped process inventory after those failed attempts found no surviving serve.py/peer.py/load.py commands from the campaign's temporary directories. No process was killed by enumeration.

```text
rtk proxy .venv/Scripts/python.exe -X utf8 plans/pr34-remediation/runtime_crash_pressure_campaign.py .git/pr34-evidence/crash-pressure-windows-final.json --cycles 6
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -X utf8 plans/pr34-remediation/runtime_crash_pressure_campaign.py .git/pr34-evidence/crash-pressure-linux-final.json --cycles 6
rtk proxy ruff check plans/pr34-remediation/runtime_crash_pressure_campaign.py
```

Platforms run sequentially. Ruff PASS. Final terminal measurements are recorded below and in the complete sanitized sample manifests. T-LIFE-04 is the scoped requirement. T-E2E-04 additionally requires combined start/stop/crash/recovery-under-load cycles and remains open; this campaign uses a fresh store for each killed owner. It does not replace comparative performance, startup-under-pressure, active-turn SIGTERM, or final full-suite qualification.

Final Windows55596 and Linux48465 both terminal exit0/PASS. Each platform completed all8 cycles (2 warmup+6 measured); both load workers exited. Measured summaries:

- windows: {"status": "PASS", "warmup_cycles": 2, "measured_cycles": 6, "min_cpu_fraction": 0.8975827988975973, "max_reap_seconds": 0.10321300000941847, "observed_peer_tree_stops": 12, "owners_terminated": 6, "max_rss_growth_bytes": 2060288, "max_descriptor_growth": 1, "max_thread_growth": 0, "exit_code": 0}
- linux: {"status": "PASS", "warmup_cycles": 2, "measured_cycles": 6, "min_cpu_fraction": 0.9911926805651599, "max_reap_seconds": 0.014393493999996565, "observed_peer_tree_stops": 18, "owners_terminated": 6, "max_rss_growth_bytes": 221184, "max_descriptor_growth": 0, "max_thread_growth": 0, "exit_code": 0}

Full samples and declared limits are in p12-crash-pressure-PLATFORM-final.json; source SHA and exact campaign hash match across platforms. No live campaign handles remain.
