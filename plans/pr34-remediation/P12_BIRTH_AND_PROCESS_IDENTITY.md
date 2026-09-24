# P12 — birth boundary and process identity

Parent `ff565eaa001eff1654300ac457d1b7be76124a7f` plus exact new fixture/test hashes in `evidence/p12-birth-identity-index.json`. Production unchanged; feature/v0.2.0.

T-LIFE-02: a disposable real owner invokes the production spawn_owned_process under RuntimeLifecycle. Its native child and grandchild are alive before a barrier either immediately before lifecycle registration (zero callbacks) or immediately afterward (one callback), before any harness protocol handshake. The parent verifies the exact owner PID is the launched base interpreter, acquires exact process handles/pidfds, kills that owner without Python cleanup, and witnesses child/grandchild plus Linux guardian stopped. Linux grandchild starts a new session to exercise adoption beyond the initial process group. Windows JOB_LIST ownership is established atomically at birth; Linux guardian inherits the owner pidfd/cancellation pipe before native launch. The logical birth/registration window is tested against these stronger kernel ownership mechanisms, not a periodic PID snapshot. Production REST handshake timeout/retry composition is separately qualified by P12_CAPTURE_AND_RECEIPTS.md; this unit tests the common launch primitive itself.

T-LIFE-05: create an owned native child and an unrelated, responsive disposable echo process. Substitute the owned Popen numeric pid metadata with that unrelated PID, call production terminate/kill, then restore metadata solely so Popen can wait for its actual child/guardian. The original native identity stops; Linux tree cleanup proof is retained; the unrelated original process still answers a new echo on the same pipe. This is a controlled simulation of stale/reused numeric identity, not a claim of inducing actual kernel PID recycling. Cleanup uses Job handles or private guardian channels, never that substituted number.

Exact fixture witnesses also perform emergency cleanup using termination-capable Windows handles/pidfd signals if an assertion fails. Only test-created identities are targeted. Parent/children have bounded lifetime and all pipes/handles are closed; no personal process/configuration/provider is used. Windows helpers are hidden.

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_birth_identity.py -q --junitxml=.git/pr34-evidence/birth-identity-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_birth_identity.py -q --junitxml=.git/pr34-evidence/birth-identity-linux.xml
rtk proxy ruff check tests/runtime_birth_window_fixture.py tests/test_runtime_birth_identity.py
rtk git diff --check
```

Terminal exit0: Windows1366 **4 PASS4.65s**, Linux48841 **4 PASS4.74s**. No failures/skips, Ruff/diff PASS. Per-node sanitized manifests in index; raw XML stays under .git/pr34-evidence. No production migration/change or new live MCP smoke requirement.

Next: remaining14 original rows, final immutable-source suites, findings/operations/release audit and build/reinstall0.2.0. Native Pi/attach remain NOT_RUN; final gate NOT PASSED.
