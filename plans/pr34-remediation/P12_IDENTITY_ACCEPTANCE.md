# P12 — exact identity acceptance coverage

2026-09-24, parent `748987e2ef111d4e7d727aa43396cb07c5a38c3a`,
feature/v0.2.0. No application contract/schema change in this unit.

The prior manual coverage review found three missing acceptance stimuli in
otherwise passing tests. `tests/test_runtime_identity_acceptance.py` exercises
the production socket app, REST/MCP authentication, canonical repositories,
endpoint/open service and presence, using only synthetic external peers.

- T-ID-01: open, close and reopen through each surface, snapshot all canonical
  Agent fields after every transition. Capabilities, metadata and role exist in
  the fixture; tags, permissions and comm_scope are explicitly configured.
  Reopening has a new session while the full Agent record remains identical.
- T-ID-02: both authenticated surfaces reject an unknown identity before factory
  invocation, with a canonical error; neither an Agent nor a session is created.
- T-ID-03: two concurrent requests for the same Agent exercise both distinct
  endpoints and the same idempotency key. The latter permits a transient conflict
  while in progress, then resolves the same binding through MCP. Exactly one or
  two peer/session records exist as appropriate; each canonical presence binding
  belongs to the original Agent/workspace. Full Agent snapshot is unchanged.

These close coverage gaps rather than reproduce a newly discovered defect.
No production correction was needed for these stimuli. They do not qualify real
native process behavior or the remaining identity catalogue/start-failure gates.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_identity_acceptance.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_identity_acceptance.py
rtk proxy ruff check tests/test_runtime_identity_acceptance.py
```

Windows:6 PASS18.13s. Linux:6 PASS23.53s.
Ruff PASS. Source hash and final execution results will accompany the milestone.
Final gate NOT PASSED. Next: remaining exact matrix mapping and current Linux
full regression, then unresolved migration/crash/load/performance/rollout gates
and final build/install0.2.0. Pi/dedicated attach native remain NOT_RUN.
