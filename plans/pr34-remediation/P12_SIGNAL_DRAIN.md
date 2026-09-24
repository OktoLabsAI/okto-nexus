# Active-turn shutdown with pending journal projection

Parent3779e95. Production code unchanged. This closes the missing joint stimulus for T-LIFE-03; existing live-session-only signal tests were insufficient alone.

`tests/test_runtime_signal_drain.py` starts the actual `serve` CLI through the existing isolated subprocess fixture. Its approved synthetic Pi peer has an independently witnessed child; Linux also witnesses the owned guardian. The peer acknowledges a prompt, starts a native turn and emits an output delta without a native final. It deliberately stays alive after EOF, so incidental pipe closure cannot substitute for owned-process cleanup.

A fixture-only gate pauses `RuntimeEventIngress.recover` before entering its SQLite work, after the real capture path has appended/fsynced the delta. The test observes its correlated event/operation identity and confirms the event is absent from SQLite, no result exists and no terminal is set. This is genuine captured-but-unprojected journal state during a real active native turn. No journal durability or product authorization is disabled.

The gate releases at the existing `HarnessSupervisor.begin_shutdown` boundary, after recording that projection remains pending. Linux sends SIGTERM to the exact owned serve process; Windows and Linux additionally exercise explicit graceful serve exit. The real shutdown coordinator must drain the journal, close it, terminate every witnessed owned process and exit within20s. The final database checkpoint must equal the closed journal watermark, the captured delta must appear exactly once with intact text, and foreign keys must remain valid.

Pi has no native end-session wire verb. Its adapter closes the process instead of promising a final turn event. Therefore the correct result for the interrupted active turn is OUTCOME_UNKNOWN/runtime_lost with no terminal/result invented. The test requires this classification and preserves the already captured delta. A clean server exit is not falsely represented as completed agent work.

## Preparation findings

- Initial Windows run:1 FAIL1 SKIP. The test wrongly required a final native result after Pi process close. Code inspection of PiRpcConnector._end and persisted events demonstrated that shutdown correctly preserved the delta and recorded uncertainty; the fixture expectation was corrected. No product RED/fix claim.
- First expanded Windows run:1 FAIL6 PASS3 SKIP. The test saw an empty marker while the fixture was still writing JSON. Markers now publish via write-to-temporary then rename; they are not product storage.
- First expanded Linux run:1 FAIL9 PASS. SIGTERM cleanup finished with exit0, while the test had assumed -15. The serve implementation deliberately installs a harmless original SIGTERM handler so Uvicorn's forwarding converges on the same cleanup/return0 path. The test still sends the real signal; only its incorrect exit-status expectation changed.
- All above handles were explicitly observed terminal before the final rerun. Their per-node diagnostic manifests are retained separately from final gates.

## Exact commands

```text
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_signal_drain.py -q --junitxml=.git/pr34-evidence/signal-drain-initial-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_signal_drain.py tests/test_runtime_shutdown.py tests/test_serve_harness_shutdown_reap.py -q --junitxml=.git/pr34-evidence/signal-drain-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_signal_drain.py tests/test_runtime_shutdown.py tests/test_serve_harness_shutdown_reap.py -q --junitxml=.git/pr34-evidence/signal-drain-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_signal_drain.py tests/test_runtime_shutdown.py tests/test_serve_harness_shutdown_reap.py -q --junitxml=.git/pr34-evidence/signal-drain-final-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_signal_drain.py tests/test_runtime_shutdown.py tests/test_serve_harness_shutdown_reap.py -q --junitxml=.git/pr34-evidence/signal-drain-final-linux.xml
rtk proxy ruff check tests/test_runtime_signal_drain.py
```

Final Windows3515 is terminal exit0:7 PASS3 SKIP30.15s. The three POSIX-only signal cases remain unexecuted on Windows; graceful Windows evidence is separate, never relabeled SIGTERM. Linux final65323 is terminal exit0:10 PASS69.88s, including the actual active-turn/pending-journal SIGTERM case. Native installed Pi is NOT_RUN; all these peers are synthetic, not provider qualification. No P12/final release gate promotion.

Final hashes and mandatory parameterized nodes were verified against the per-node manifests in the [acceptance index](evidence/p12-signal-drain-index.json). Ruff and git diff --check PASS. T-LIFE-03 is scoped PASS on supported OS paths; Windows POSIX cases stay NOT_RUN/SKIP. No execution handles remain live. Next: complete the remaining original-matrix coverage review and final immutable-source regressions, operational finding index and release build/reinstall.
