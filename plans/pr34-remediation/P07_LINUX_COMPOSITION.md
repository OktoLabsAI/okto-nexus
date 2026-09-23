# P07 — Linux composition qualification

Implemented unit, parent 3c0eb84, feature/v0.2.0, 2026-09-23.
No migration. Full plan/final gate remains open.

An isolated supported Python was provisioned with:

```
rtk proxy powershell -NoProfile -Command '$runtimeHome = Join-Path $env:TEMP "okto-pr34-linux-python"; uv python install cpython-3.13-linux-x86_64-gnu --install-dir $runtimeHome --no-bin --no-registry'
rtk proxy powershell -NoProfile -Command 'uv export --frozen --extra dev --no-emit-project --no-hashes --output-file (Join-Path $env:TEMP "okto-pr34-linux-requirements.txt") | Out-Null'
```

CPython 3.13.12, WSL Ubuntu x86-64/kernel 5.15.146.1, repository locked dev
dependencies. No provider configuration or native account was used. Initial venv
under /tmp was absent on the next invocation; /var/tmp was used subsequently.
The initial interpreter on the Windows mount also made sub-second fixture
handshakes unreliable. A copy of the same interpreter was placed in
`/var/tmp/okto-pr34-native-python-q84f5fav/python`, and its isolated `venv` uses
the exported requirements plus `pip install --no-deps -e` of this repository.
This is a Linux test install, not the requested final Windows local reinstall.

The first integrated attempt produced **99 FAIL / 51 PASS / 18 skipped**, 119.04s:
`evidence/p07-linux-composition-initial-failure.log`. Most failures correctly
refused ownership because this standalone Python build omits os.pidfd_open despite
the kernel supporting it. The initial environment also lacked the editable
package needed by a separate stdio producer. No failed/skipped cases are counted
as passing.

Corrections:

- Native Python pidfd wrappers remain preferred. If absent, a narrowly gated
  Linux x86-64 ABI wrapper calls the same kernel pidfd syscalls, with errno
  propagation and close-on-exec descriptors. There is no fallback to process-name
  scans or unverified PIDs, and unsupported ABIs/kernels fail closed.
- Native executable validation precedes guardian creation, preserving missing
  binary/permission errors instead of presenting a later protocol EOF. This
  preflight does not guarantee a later exec will succeed.
- Unexpected RuntimeOpenService errors now use the canonical OktoNexusError path.
  A reply-persistence fault remains uncertain/idempotent, while the HTTP client
  can retry the same request without an unhandled ASGI exception/reset. The
  strengthened Windows test reproduced INTERNAL instead of INTERNAL_ERROR before
  correction (1 FAIL / 13 deselected, 3.54s).
- The guardian releases its inherited stdin/stdout/stderr copies after native
  spawn. Its copies previously masked native EOF while the process stayed alive:
  the second Linux gate had 1 FAIL / 156 PASS / 12 skipped, 228.72s, in Claude's
  existing EOF-without-exit regression. See p07-linux-composition-eof-failure.log.
  The added component check observes native EOF while poll still reports running;
  the existing Claude regression now completes without fabricating process exit.

ABI source: [Linux v6.12 x86-64 syscall table](https://github.com/torvalds/linux/blob/v6.12/arch/x86/entry/syscalls/syscall_64.tbl)
and [pidfd_open manual](https://man7.org/linux/man-pages/man2/pidfd_open.2.html).
Only x86-64 raw syscall fallback is qualified; other architectures need the
native Python wrapper and their own integration evidence.

Evidence so far:

- Windows regression (before the final Linux-only EOF correction): **37 PASS / 7 skipped**, 53.59s;
  `evidence/p07-linux-portability-windows.log` records the exact command.
- POSIX attach AF_UNIX fixture suite: **57 PASS**, 4.19s;
  `evidence/p07-linux-attach-fixture.log` records the exact WSL command.
  This is fabricated registry/token/socket data, not a real Claude attach session.
- Final expanded Linux composition gate: **215 PASS / 12 skipped / 1 known injected
  Pi callback warning / 2 subtests PASS**, 209.97s. Exact command in
  `evidence/p07-linux-composition-gate.log`; includes all four connector fixture
  suites, production HTTP/MCP/stdin/outbox/restart/journal/ownership paths.
- Focused EOF/component correction: 9 PASS / 34 deselected / 2 subtests PASS,
  14.08s, before the expanded final gate. Ruff and diff whitespace checks PASS.
- Native Pi/attach remain NOT_RUN by campaign scope. No native Codex/Claude
  provider campaign ran in this Linux unit.
- Windows compatibility inventory, not a final/full gate: **20 FAIL / 764 PASS /
  68 skipped / 2 warnings**, 177.79s, stopped intentionally at 20 failures;
  `evidence/p12-compatibility-inventory.log`. Two legacy POSIX serve-signal files
  were NOT_RUN on Windows because their process/signal assumptions are unsafe
  there. Early failures include obsolete auto-registration, ambient backend and
  unauthenticated/default-enabled harness expectations; fixtures/assertions need
  adaptation to the approved identity/auth/profile composition. No relaxation of
  the production safeguards is authorized by those old tests.

Changed symbols: linux_process_guardian.pidfd_open/pidfd_send_signal and ABI
wrapper and native pipe ownership; OwnedLinuxPopen executable preflight; RuntimeOpenService error mapping;
Linux ownership and open-idempotency regressions. Remaining P07 includes stable
boot, stale runtime reconciliation, and the broader control/crash matrix.
