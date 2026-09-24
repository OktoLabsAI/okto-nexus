# P12 — uncaptured result, recovered receipts and bounded workers

Parent `3c61a859c07d45604ec889bcc66ee52e1060ad6d` plus changed fixture/test hashes in `evidence/p12-capture-worker-index.json`. Production unchanged, branch feature/v0.2.0.

## Original acceptance joins

**T-JRN-10**: actual owner process exits78 before FileRuntimeEventJournal.append for either the first correlated native output_delta or the terminal event. The fixture marker records only correlation/phase/watermark and never becomes a replay source. The exact native process handle/pidfd is witnessed stopped. Restart on the same temporary store advances only application clock, recovers the original attempt as OUTCOME_UNKNOWN, quarantines its endpoint and exposes result_durable=false through authenticated MCP. No result, processing receipt, terminal completion or second native process/send appears; inbox remains unread with its push reservation. Earlier deltas may survive in the terminal-cut variant; they do not authorize inventing a result. Without protocol replay, bytes not captured durably cannot be recovered.

**T-CONS-08**: extend the real after-commit owner-crash test (with/without forced stopped-store checkpoint rewind). One canonical processing receipt survives alongside the one correlated result/publication. It explicitly says human_read=false. The authenticated original caller pulls and ACKs this recovered receipt twice: acknowledged1 then0. Exactly three messages and one original outbox remain; no receipt cascade or extra execution. This tests the real HTTP/MCP recovery composition, not only standalone inbox mocks. Projection/checkpoint remain atomic as documented in P12_PROJECTION_COMMIT_CRASH.md.

**T-DISP-07**: reread and execute existing bounded-worker assertions: four noncancelable starts retain four quarantined slots; fifth start is refused. Four blocked controls retain slots; fifth refused. Explicit fixture release allows cleanup with no live sessions. Real REST/Codex handshake-timeout case leaves no RUNNING row, preserves identity and repeating its key cannot respawn. Production factory test holds a transport stack even after its actual native result: operation remains in-flight, another endpoint for that agent waits, and a healthy agent progresses before release. This proves bounds/containment, not forced cancellation of a stuck Python thread.

## Commands and terminal outcomes

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_uncaptured_result_crash.py tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/uncaptured-result-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_process_ownership.py::test_wedged_starts_and_controls_hold_bounded_slots tests/test_runtime_process_ownership.py::test_rest_owner_start_timeout_has_no_running_session tests/test_runtime_worker_capacity.py -q --junitxml=.git/pr34-evidence/wedged-worker-review-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/recovered-receipt-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_uncaptured_result_crash.py tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/uncaptured-result-linux.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_process_ownership.py::test_wedged_starts_and_controls_hold_bounded_slots tests/test_runtime_process_ownership.py::test_rest_owner_start_timeout_has_no_running_session tests/test_runtime_worker_capacity.py -q --junitxml=.git/pr34-evidence/wedged-worker-review-linux.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_projection_commit_crash.py -q --junitxml=.git/pr34-evidence/recovered-receipt-linux.xml
rtk proxy ruff check tests/runtime_relay_process_fixture.py tests/test_runtime_uncaptured_result_crash.py tests/test_runtime_projection_commit_crash.py
rtk git diff --check
```

- Initial capture/projection regression: Windows64846 **4 PASS61.97s**, Linux93726 **4 PASS85.29s**.
- Bounded-worker review: Windows41685 **3 PASS19.65s**, Linux6353 **3 PASS27.79s**.
- Extended recovered-receipt cases: Windows94708 **2 PASS39.80s**, Linux81394 **2 PASS48.95s**.

All six handles terminal exit0, no failures/skips. Seven distinct nodes/platform across these runs; the projection cases are repeated, not additional distinct tests. Ruff/diff PASS. Sanitized manifests retain per-node results; raw XML remains under .git/pr34-evidence. No production change/live MCP smoke required, no installed provider campaign.

Next: remaining20 original matrix rows; then immutable-source full suites, finding/operational/release audit and local build/reinstall0.2.0. Native Pi/attach remain NOT_RUN. Final gate remains NOT PASSED.
