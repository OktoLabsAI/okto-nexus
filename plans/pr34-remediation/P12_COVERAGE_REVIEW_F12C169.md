# P12 — consumption and lifecycle coverage review

Source: `f12c169a81b2af56ca351194f136d6e96f113fa5`, branch `feature/v0.2.0`. Production and tests unchanged during these runs. Protected local dashboard assets are outside this selection. This is a selected gate, not the final full-suite or native gate.

Manual assertion review is in `evidence/p12-coverage-review-f12c169.json`. Complete coverage must be joined to terminal per-node PASS results before promoting the original matrix. No provider/model or installed harness is used: HTTP/MCP production composition runs in disposable stores with synthetic protocol peers; selected stdio tests start real isolated Nexus processes.

## Commands and execution

Consumption selection:

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_outbox.py tests/test_runtime_commands.py tests/test_runtime_safe_retry.py tests/test_runtime_operation_reconciliation.py -q --junitxml=.git/pr34-evidence/consumption-review-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_outbox.py tests/test_runtime_commands.py tests/test_runtime_safe_retry.py tests/test_runtime_operation_reconciliation.py -q --junitxml=.git/pr34-evidence/consumption-review-linux.xml
```

Lifecycle selection:

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_boot.py tests/test_runtime_shared_connection.py tests/test_runtime_production_multiplex.py tests/test_runtime_protocol_compatibility.py tests/test_runtime_session_recovery.py -q --junitxml=.git/pr34-evidence/lifecycle-review-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_boot.py tests/test_runtime_shared_connection.py tests/test_runtime_production_multiplex.py tests/test_runtime_protocol_compatibility.py tests/test_runtime_session_recovery.py -q --junitxml=.git/pr34-evidence/lifecycle-review-linux.xml
```

Terminal exit0 for all four processes: consumption Windows42914 **54 PASS220.09s**, Linux81505 **54 PASS226.37s**; lifecycle Windows48869 **37 PASS154.43s**, Linux51952 **37 PASS165.07s**. One pre-existing Starlette TestClient deprecation warning per consumption run. No failures/skips. There are91 distinct nodes per platform, not182 independent cases. Sanitized per-node manifests and `evidence/p12-coverage-review-f12c169-index.json` retain the exact joins. Raw XML is preserved under `.git/pr34-evidence/`; no captured logs or credentials are committed. Seven requirements promoted, three reviewed partial requirements retained NOT_RUN.

## Reviewed limitations and next dependencies

- T-CONS-05 validates explicit operator risk acceptance and release of the same inbox, preserving uncertain transport history. It does not promise exactly-once execution.
- T-DISP-08 combines lane ordering with urgent control and stale-turn fencing. It does not promise cancellation of arbitrary blocked OS calls.
- T-LIFE-01/07/08/12 cover stable boot, concurrent close/final capture, shared Codex process isolation and fail-closed protocol drift. Peers are synthetic; native qualification remains separately reported.
- T-PRES-03 restores a persisted crash cut, then starts the production owner. Historical RUNNING cannot sustain presence. It does not itself kill a real owner; exact death campaigns remain separate evidence.
- T-TX-03 remains partial: existing concurrent open/recovery and serial send tests do not jointly prove concurrent send admission, one grant charge and one native effect.
- T-TX-04 remains partial: changed metadata/content are covered; changed target/context and immutable original payload require explicit assertions.
- T-CONS-06 remains partial: safe lane-busy retry is not a socket failure, and its current tests do not inspect the inbox attempt/lease invariants.

No shared contract changes, migrations or live MCP smoke are required for this documentation-only mapping unit. Next: resolve remaining exact-stimulus coverage gaps, then final committed-source Windows/Linux suite, finding index and release/build/reinstall checks. Pi and dedicated attach native gates remain NOT_RUN under the current operator configuration.
