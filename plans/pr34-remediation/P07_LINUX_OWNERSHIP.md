# P07 — Linux birth ownership and observable tree cleanup

2026-09-23, parent SHA 920faee, feature/v0.2.0. No migration. P07 IN_PROGRESS.

The existing POSIX new-process-group launch did not survive owner SIGKILL. A real
disposable Python owner/child/escaped-grandchild test reproduced the orphan:
1 FAIL in 5.358s, evidence/p07-linux-ownership-red.log. Cleanup of that deliberate
failure used pidfds captured while the fixture processes were alive, never an
unverified PID from an old log. No provider/account/session was used in Linux.

OwnedLinuxPopen now starts one isolated Python guardian per native connection,
passing an owner pidfd, cancellation pipe and cleanup-proof pipe before any
native launch. The guardian becomes a subreaper before spawning, creates a native
process session, and monitors owner death through the kernel pidfd. Native exec
does not inherit guardian descriptors. Cleanup kills the still-unreaped leader's
group and adopted direct children, then reaps until ECHILD before reporting proof.
Only this guardian reaps those children, so their PIDs cannot be recycled during
signalling. No global process-name scan, cached PID ancestry or unrelated orphan
selection is used. An unrelated fixture process survives the tests.

terminate requests SIGTERM for the native group; kill/owner death forces cleanup.
The guardian remains alive for an unkillable child instead of falsely confirming
stop. A guardian itself externally SIGKILLed cannot prove tree cleanup: observed
state remains unknown. This is process ownership, not an OS sandbox or protection
against a privileged actor deliberately killing the guardian. There is a hard
per-Nexus-process cap of 32 owned Linux connections; slots are released only on
observed cleanup or pre-spawn failure, not by an unknown helper exit. The existing
supervisor applies its stricter live/startup limits as well.

All three managed adapters use spawn_owned_process. Pi close now calls the owned
handle methods instead of signalling a freshly looked-up process group. Windows
Job ownership is unchanged. serve's compatibility watchdog hook no longer launches
the historical ps/PID scanner. The historical standalone watchdog code/tests remain
to be retired/adapted in the final compatibility pass; they are not production
ownership evidence. Attach never enters managed process cleanup.

Managed platform declaration is Windows/Linux; other POSIX managed launches now
fail explicitly before effects. POSIX attach retains its separate platform contract.
Linux needs pidfd support; failure to obtain required primitives prevents admission.

Changed symbols/files: linux_process.OwnedLinuxPopen, linux_process_guardian.run;
owned_process.spawn_owned_process/observe_owned_process; Pi transport close;
serve._spawn_harness_orphan_watchdog; platform catalog; Linux ownership/platform tests.

Evidence and commands (executed via rtk proxy):

- `wsl -d Ubuntu --exec python3 /mnt/d/Projetos/Techridy/okto_labs_okto_nexus/tests/test_linux_process_ownership.py -v`:
  final **6 PASS in 1.547s**, evidence/p07-linux-ownership-gate.log. Earlier progress
  logs are explicitly narrower (1 and 3 tests). Tests cover owner SIGKILL with an
  escaped grandchild, natural leader exit, bystander survival, FD isolation, native
  graceful exit status, descriptor-allocation failure, bounded admission, and missing
  proof after deliberate guardian SIGKILL. Linux 5.15.146.1-microsoft-standard-WSL2,
  Python 3.10.12, Ubuntu. This standalone stdlib component run is NOT a claim that
  full Nexus supports Python 3.10; full application Linux integration requires an
  isolated supported Python >=3.11 environment and remains NOT_RUN here.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_process_ownership.py tests/test_runtime_shared_connection.py tests/test_runtime_protocol_limits.py tests/test_runtime_contracts.py tests/test_runtime_attach_platform.py tests/test_linux_process_ownership.py tests/test_harness_pi_connector.py -q --tb=short`:
  Windows **61 PASS, 5 skipped, 1 known injected Pi callback warning, 35.03s**;
  evidence/p07-linux-windows-regression.log. This run preceded adding the final
  Linux graceful-exit/capacity cases; it does not claim those executed on Windows.
- `.venv/Scripts/python.exe -m pytest tests/test_runtime_attach_platform.py tests/test_runtime_contracts.py tests/test_runtime_process_ownership.py tests/test_linux_process_ownership.py -q --tb=short`:
  Windows **22 PASS, 5 skipped, 7.69s**, evidence/p07-linux-platform-gate.log;
  preceded the last Linux-only capacity case. Unsupported managed platform rejection
  and catalog are covered. Skips mean NOT_RUN on that host.

Ruff and diff checks PASS. No native Codex/Claude/Pi/attach campaign was run for
this ownership unit. Previous Windows native evidence retains its own SHA/scope.

Foundations (primary Linux man-pages, inspected 2026-09-23):
[subreaper adoption](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html),
[wait/waitid and unreaped children](https://man7.org/linux/man-pages/man2/waitid.2.html).
The decision to use a per-connection guardian/proof protocol is new implementation,
not a claim that these primitives supply a cgroup or native sandbox.

Remaining: full supported-Python Linux composition, scheduler-pressure/kill matrix,
global shutdown budget, stale runtime/boot recovery, durable controls/steering,
publication/causal budgets/managed-work integration and final release gates.
