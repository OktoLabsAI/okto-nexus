# Descriptor capability admission

Parent SHA: `2785c65d400d21bb53a1b6b6f6e5ae80e4b6286f`; feature/v0.2.0. Schema remains 057; MCP surface 51, identity reference 18. Final gate NOT PASSED.

## Finding and implementation

The fifth processless adapter could register `conversation=False` yet receive canonical message transport reservations and direct turns through both REST and MCP. Three behavioral regressions failed against the existing production composition: **3 FAIL**, 8.55 s. The connector still supported writing bytes, which must not override the trusted descriptor's capability restriction.

`RuntimeDeliveryPlanner.enqueue` now excludes nonconversational descriptors; the canonical message and unread delivery remain in the inbox without a push reservation. `revalidate` checks again before durable send-intent. `RuntimeControlService.send` and `validate` apply the shared `validate_declared_command` guard to turns, steering and interruption. This is additional to authentication, grants, native control evidence and native turn fencing. Close remains available for cleanup. No product enum, registry loader, schema migration or new transport queue was added.

The new `additional_readonly` fixture configures the trusted descriptor before constructing the actual HTTP/MCP app. Tests do not patch private admission methods. A restart test admits a pending operation with the original descriptor, drains the owner, registers the restricted descriptor in the replacement composition and verifies rejection with ACK NONE before connector construction. No prompt is replayed.

## Validation

All commands run in the repository, with isolated fixtures and no provider credentials.

- RED: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_capability_admission.py`: **3 FAIL**, 8.55 s.
- Intermediate: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_capability_admission.py tests/test_runtime_contracts.py tests/test_pr34_remediation.py tests/test_runtime_commands.py`: **61 PASS / 1 FAIL**, 117.01 s. Only the new inbox assertion was wrong after the behavior was fixed: the established response omits `runtime_operations` when empty. It now accepts the omitted field while still requiring no outbox/reservation/native send in the database and connector assertions.
- `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_runtime_capability_admission.py tests/test_runtime_contracts.py`: **15 PASS**, 9.90 s, one known Starlette warning, including the restart case.
- Final Windows: `rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short tests/test_feature_flags.py tests/test_frente1_resources.py tests/test_runtime_capability_admission.py tests/test_import_boundary.py`: **62 PASS**, 25.40 s, one known Starlette warning.
- Linux: `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short tests/test_runtime_capability_admission.py tests/test_runtime_contracts.py`: **15 PASS**, 19.87 s, one warning.
- Ruff on the three changed application modules and two fixture/test modules: PASS. `rtk git diff --check`: PASS.
- `rtk proxy .venv/Scripts/python.exe plans/pr34-remediation/measure_surface.py 2785c65`: OFF unchanged at 43 tools / 40448 resident characters; ON unchanged at 51 / 47730. Revision metadata 50 to 51.

Native Codex/Claude/Pi/attach campaigns in this unit: **NOT_RUN**. The existing four enabled connector fixtures passed in the broader selection; prior native evidence remains scoped to its own SHA/configuration.

## Remaining dependency

This closes a declared-capability bypass, not the entire effective-capability requirement. Unknown native versions/configurations still require a complete per-session intersection of adapter support, observed/qualified native contracts and approved profile restrictions. Discovery currently labels declarations and compatibility observations honestly and must not be promoted to full verification without that enforcement. Broader qualification, final matrix/performance checks and build/reinstall remain pending.
