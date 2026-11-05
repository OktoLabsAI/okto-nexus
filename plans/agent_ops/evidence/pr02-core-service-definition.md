# PR-02 — shared Windows user-service definition

Core now supplies a pure immutable descriptor, Windows logon-task XML renderer
and fingerprint of native exported definitions. There are no OS effects or
credentials in the module. Host adapters will own registration, compare-before-
mutation, stable execution context and drain before supervisor control.

13 Core tests passed on Windows 11 / Python 3.13.1. They cover unique instance
names, effective SID, literal quoting/XML escaping, bounded failure retries,
rejection of ambiguous paths, and preservation of unknown user edits in the
definition fingerprint. Native Task Scheduler validation used only
`TASK_VALIDATE_ONLY`, with task absence verified before and after. No task was
registered, enabled or started. Native validation initially detected a conflicting
UTF-8 XML declaration through Unicode COM; omitting it fixed the actual API path.

Command (RTK, from Core):
`python -X utf8 -c "import sys; sys.path.insert(0,'src'); import pytest; raise SystemExit(pytest.main(['tests/test_user_service_definition.py','tests/test_public_docs.py','-q','-x','--junitxml=<Nexus>/plans/agent_ops/evidence/pr02-core-service-definition.xml']))"`.
Scoped Ruff passed. Candidate wheel contains all 130 matching Python source
files, is byte-identical in both consumers, and its new module imports from the
installed wheel. Nexus lock/manifest coordinated with the candidate.

Core wheel SHA-256:
`1169d898a32cbc10e12c47dc88b12e0594d74c7f6d76ebcc8b3da07123a5942d`.

Microsoft references:
[schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[validate-only flags](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/ne-taskschd-task_creation),
[registration/logon contract](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertask).

This verifies syntax/definition behavior only. Host integration, installed
supervisor lifecycle, real login/terminal/logout recovery and credentials remain
open. No SVC acceptance campaign is marked complete from XML generation.
