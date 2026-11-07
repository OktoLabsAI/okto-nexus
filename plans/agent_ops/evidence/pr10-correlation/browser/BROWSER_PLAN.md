# OBS12 installed browser scenario — prepared, not executed

This directory contains a new disposable scenario. No old private fixture was read, copied or hashed. Scripts have only been parsed; no Server, browser, provider or real OS process-proof operation has been started.

The canonical fixture is synthetic: explicit valid canonical rows, a synthetic birth proof stored through `SqliteObservationCorrelationRepo`, and synthetic frames accepted by the real `append_execution_receipt` producer. This qualifies HTTP projection and installed UI rendering only. Native process/Core qualification remains in the dedicated tests. Do not report this fixture as a real process proof.

## Inputs and launch after the root's GO

Required inputs are a wheel containing the frozen OBS12 sources/static assets, its isolated installed venv, the shared dependency site used by that venv, and the checkout root to exclude from import resolution. The scripts do not build/install anything. Use an ordinary Python to configure/start; use the **installed venv Python** for fixture seeding.

From this directory (all shell commands must retain the RTK prefix):

```powershell
rtk proxy <python> configure.py --venv <installed-venv> --dependency-site <dependency-site> --checkout-root D:/Projetos/Techridy/okto_labs_okto_nexus --wheel <frozen-wheel>
rtk proxy <python> start_server.py
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py initial
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py check
```

`start_server.py` creates only `qualified/server-home`, strips inherited application/provider variables, starts the installed CLI with a hidden process, empty discovery, embedding/memory/harness disabled, and records readiness and canonical service ownership. Runtime composition and journal opening are explicitly guarded. `server-import-proof.json` verifies every imported Nexus/Core module was loaded from the configured installed venv site. If start/readiness fails, retain metadata and stop through the canonical protocol when possible; never kill an arbitrary PID.

Read only `qualified/server.json` for the loopback origin and `qualified/browser-fixture-metadata.json` for the four exact IDs. **Do not read, copy, hash or export the private bearer registry, DB, WAL or SHM.** Fresh capability bearers are retained only for this new scenario.

The initial API check requires both exact detail and paginated current list to show all four valid correlations, session lifecycle `READY`, last receipt `SUCCEEDED` with `core_committed`, external `working`/`blocked` unchanged, and a total of four external instances. The Server's returned metadata is saved with no bearers.

## Browser procedure

The parent may use its existing browser-control surface. A Playwright CLI wrapper `pwcli.ps1` is also prepared; `npx` was found at `C:/Program Files/nodejs/npx.ps1`. The wrapper has **not** been executed. Run it from this Temp directory so generated artifacts remain local to the scenario.

```powershell
rtk proxy powershell -NoProfile -File ./pwcli.ps1 open <origin> --headed
rtk proxy powershell -NoProfile -File ./pwcli.ps1 snapshot
```

Use fresh snapshot element refs for all clicks; placeholders below must be replaced from that snapshot. Re-snapshot after changing tabs, opening/closing a modal, or refreshing data. Capture screenshots for the listed checkpoints. Do not open agent key issuance, execute controls, or paste bearer material into the browser.

1. Open **Agents** and locate agent `observed` in `obs-workspace` (or All workspaces). Verify its **External activity** summary says one working and three awaiting input, separate from canonical presence/capacity. Expand **Inspect external instances**. The current list must contain the four IDs from public metadata.
2. In both working and blocked instances, verify **Canonical session facts** appears before **External activity report**. Check **Recorded session lifecycle: READY**, then a separate **Last receipt received: SUCCEEDED**, operation `synthetic-received-turn`, and the three provenance descriptions. Working remains Working; blocked remains Awaiting input. No Idle, online or capacity assertion may be derived from the receipt.
3. Verify the `javascript:`/HTML-looking source reference and `<svg ...>` reason are literal text. No link/command/action is created from them. Canonical references have no approve/dispatch control. Capture the expanded instance.
4. Open **Attention** and select the **Inspect external observation** action for the `blocked` instance, matching its exact public ID, not the first row. The inspector must show the same canonical-first order and receipt/lifecycle distinction. Capture it.
5. While the blocked inspector is open, execute the controlled mutation below, then click **Refresh observation** using a fresh snapshot ref. Its canonical reference and receipt must disappear; the external report remains consultable. Refresh Agents instances as well. This tests DTO replacement with null, not a cosmetic browser-only change.

```powershell
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py clear blocked
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py check
```

6. Open the `generation` instance's Attention inspector. Rotate only that synthetic instance, then refresh the still-open inspector. The old generation must be refused and old canonical data cleared. Close the modal, refresh Agents instances, and confirm the new generation has no canonical ref. Capture both the selection-fence notice and refreshed list.

```powershell
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py rotate generation
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py check
```

7. Open the `source` instance and change its source revision by disabling only that source. Refresh inspection/current list. The DTO must contain null canonical ref/observation and the unavailable external activity must not become idle. Capture the refreshed state.

```powershell
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py source-revision source
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py check
```

8. Verify reads and observation-only mutations left the 13 selected canonical tables unchanged. This comparison excludes authentication stores and observation/attention metadata; it includes sessions, operations, leases, dispatch and receipt facts.

```powershell
rtk proxy <installed-venv>/Scripts/python.exe -B browser_fixture.py proof
```

For DOM-only evidence after taking a fresh snapshot, the following stable labels/test IDs can be inspected: `external-activity-observed`, `external-instance-<public-id>`, `external-observation-inspection`, `canonical-observation-facts`; section labels **Canonical session facts** and **Last receipt received**. Do not replace real UI interactions with mocked requests or injected DOM state.

## Cleanup and evidence limits

Close the named browser session/tab and record its close. Then:

```powershell
rtk proxy powershell -NoProfile -File ./pwcli.ps1 close
rtk proxy <python> stop_server.py
```

The stop driver opens a process synchronization handle, rechecks exact service PID/instance/generation against `server-owner.json`, requests canonical `/api/v1/service/stop`, waits for that held process to exit, verifies the listener no longer accepts connections, and closes the handle in `finally`. Never substitute a broad process kill or a recycled PID.

Retain public screenshots, snapshots, configuration/wheel hash, import proof, synthetic fixture provenance, API projections, canonical comparison, and cleanup report. Report any skipped checkpoint explicitly. There is no runtime acceptance claim until these commands and browser checks have actually run.
