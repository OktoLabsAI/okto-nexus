# Read-only review: fixture authority and installed child provenance

No product, tests, CI runner, prefix, ledger or Core files were changed for this review. No new test/application process was started. The baseline/candidate failures and interrupted shard remain antecedent evidence; this note does not reclassify them as passes.

## 1. Disabling a CLI-pinned feature is the wrong precondition for the intended test

The exact chain is `test_canonical_admission_shutdown.py:61` → `test_canonical_delivery.connected_local:13` → `test_local_realization.local_setup:20` → `test_embedded_inventory.app_for:17`. `app_for` passes `--feature-harness-integrations true` explicitly.

`config.py:832` records the presence of the flag in `_explicit_fields`, including a value equal to the default. `settings.detect_pinned_fields:750` preserves this explicit choice. `SettingsService.update:637` rejects a pinned key before writing; `http/routes.py:3659` maps that configuration refusal to HTTP 422. `http/app.py:579` constructs the real service with these detected pins. The test's assertion of HTTP 200 therefore contradicts its own fixture. The independently reproduced identical PR27 failure supports that this is not a Quick Connect regression; the source contract itself establishes the oracle error.

Minimal test-only correction after all original shards finish:

1. Give only `test_feature_disable_preserves_unprojected_terminal_and_exclusive_claim` a `mutable_connected_local` fixture. Leave the shared `app_for` default and its other callers unchanged.
2. In that fixture, reuse `local_setup.__wrapped__` and `connected_local.__wrapped__`, retaining their normal generator cleanup and synthetic native boundary. Override the **test module's app constructor** to call `bootstrap({}, ['--home', own_home, '--runtime-handoff-auto-claim-enabled', 'false'])` and `build_app`. Omit the feature flag rather than clearing `_pinned`, mutating `_explicit_fields`, replacing SettingsService, or weakening production validation.
3. Before sending work, GET settings and assert `feature_harness_integrations.value is True`, `editable is True`, and `source == 'default'` under the current default. If the default changes, prepare a stored override through the ordinary SettingsService before app startup, not a CLI/environment pin; assert the returned source explicitly.
4. Keep the existing captured-event barrier, PATCH false, admission denial, no premature publication, retained terminal and exclusive claim assertions. Add a small pinned negative that retains HTTP 422 and unchanged policy. Existing analogous contracts are `tests/test_feature_flags.py::test_env_pinned_feature_flag_is_read_only` and `tests/test_settings_api.py::test_cli_pinned_setting_is_read_only`.

This restores the intended **mutable Server policy** proof layer. It must not turn the CLI pin into an editable policy merely to satisfy the test.

## 2. Late structured completion: a second native factory has drifted

`test_canonical_handoff_recovery.py:182` calls `test_canonical_structured_work.native_work`. Its local `Factory.open` at line 35 accepts only `stream_epoch`, constructs a bare Codex Python peer, invokes `peer.start`, and wraps it directly. It does not reuse `test_canonical_native_protocol_regressions.install_native`.

The existing shared helper at `test_canonical_native_protocol_regressions.py:16` already models the current opening contract: explicit opening guard, process launch identity, process birth recorder, bounded owned-peer cleanup, and synthetic `initialized`/`account/read` responses. It represents an unauthenticated inert Python peer; it does not read a real account. The structured-work duplicate lacks those integrations. `_FAKE_SERVER_SOURCE` is a legacy wire fixture; the helper explicitly supplies its missing account handshake.

Important limit: Core `runtime.py:422` introspects the factory signature and `runtime.py:548` passes optional hooks only when declared. There is no demonstrated forwarding proxy in this current path. Therefore **missing kwargs alone do not establish a TypeError**. The exact first exception still requires the already planned bounded failed-call capture. No assertion about a Core defect, native launch, claim recovery bug or malformed terminal frame is justified from the teardown stack alone. `CopiedAdapterSession.redactor` is optional, so its omission is also not a proven constructor error.

Smallest proposed correction, conditional on the focal's first failure matching this seam: retain the structured output source transformation, then call `install_native(connected, transformed_source)` and reuse its returned peer list. Remove the duplicate factory instead of adding permissive `**kwargs` that discards authority hooks. This is a test-helper change only; do not relax Core, receipts, claim epochs, completion authority, or native protocol validation.

Before any rerun, preserve the current interrupted shard/stack and require the finite outer runner's exact process-tree cleanup. The corrected fixture should fail startup conclusively through the existing owned-peer helper when applicable; it must not manufacture a successful receipt or erase an uncertain opening to make teardown finish. Qualify both structured-work helper callers and the late-reclaimed-work node after the originals stop, not by running an unbounded broad suite again.

## 3. Installed subprocess provenance requires an explicit mode and child proof

`tools/ci_installed.py:140` verifies all three installed payloads in an independent `-I` subprocess. Lines 180–190 create pytest configuration without checkout `pythonpath`, start pytest with `-I`, and run from a temporary cwd. This strongly proves the parent/import entry cut; it does **not automatically control new subprocess launchers inside individual tests**.

Different cases must remain distinct:

| Existing source | What it actually does | Consequence |
|---|---|---|
| `tests/test_runtime_relay_process_restart.py:29` | Sets `PYTHONPATH` to `Path(__file__).parents[1]/src` plus tests, launches Python without `-I` | A real checkout run can import source. In a fixture copy deliberately lacking `src`, that first path may not exist and the child can still load the installed package. A string match alone does not prove contamination. |
| `tests/runtime_serve_shutdown_fixture.py:107` | Derives the product path from the already imported `okto_nexus.__file__`; also adds the fixture directory | In installed parent mode the selected product path is installed, not intrinsically checkout source. Record actual origins and guard fixture paths against shadowing product packages. |
| `tests/execution_r4/test_service_restart_contracts.py:54–70,130` | Uses `_base_executable` to own the actual Windows process handle; inserts selected product paths, and appends both venv and **user** site paths | Product paths may be correct, but explicit user-site fallback and base global dependencies can weaken isolation. Preserve the birth/handle invariant; do not blindly switch to the redirector executable. |
| `tests/execution_r4/test_canonical_native_protocol_regressions.py:42` and other `_FAKE_SERVER_SOURCE` peers | Start a standalone Python JSON-RPC fixture that need not import Nexus | A synthetic boundary is not a source-product process. Do not replace every Python fake or call it a real harness. |
| `tests/conftest.py:145` | Uses the current interpreter, no `-I`, copies environment | A parent `-I` does not remove inherited PYTHONPATH from environment for the next process. Current sanitized runner environments may already prevent this; the child needs evidence. |

Minimal future patch:

* Add one **test-only** child-launch helper and an explicit installed-mode option/fixture supplied by the CI runner. It should validate the expected prefix and artifact identity; no global monkeypatch of subprocess and no production feature flag.
* For ordinary product children, use the current qualified interpreter with `-I -B`, independent cwd and a sanitized environment. Remove PYTHONPATH/PYTHONHOME and personal/provider variables. Add fixture-only paths explicitly when required, with a guard rejecting `okto_nexus`, `nexus_connector_core` or Connector imports outside the approved prefix.
* For the exact-birth Windows test, keep its base executable, but build a minimal child import path from standard-library roots plus the selected qualified venv's site-packages and required subdirectories. Remove explicit user-site and unrelated base-global site-packages; verify the resulting paths/origins before serve effects. Preserve the existing process-handle/birth assertions.
* Have each actual product child emit a metadata-only origin receipt: executable/prefix, module origins, approved wheel fingerprints, and relevant payload equality. No credentials, environment values or provider configuration. Source mode remains available explicitly for development tests; label its evidence honestly.
* Initially adapt only actual product-child fixtures listed above. Keep standalone protocol peers unchanged unless they themselves import product/Core, in which case guard those imports separately. Add a negative with a tempting checkout `src`/user-site package and prove installed mode refuses it rather than silently removing failing evidence.

For the current campaign, retain per-node provenance exceptions. If a child really used checkout bytes already proved equal to the wheel, that can support an explicit hybrid code-behavior claim, not an installed-package/resource-resolution claim. If copied fixtures contain no `src`, record that and the actual child origins; do not infer either success or contamination from PYTHONPATH text alone.

## 4. Additional failures: source-backed hypotheses, not conclusions

`test_canonical_capture_admission.py:139` waits for the first terminal event to be present in **Server ingress**, then immediately shrinks the Core journal to eight rows. `embedded_events.py:121–137` commits Server ingress and only afterwards awaits `journal.acknowledge_events`; Core `journal.py:1646` persists the separate `event_streams.acked_sequence`. Server visibility therefore does not prove that the normal publisher's Core ACK is already durable. That is a concrete missing precondition for a test named “compacts ACKed events,” not proof that compaction is broken.

After the failure trace is available, a minimal fixture-only improvement may poll the scoped Core `event_streams.acked_sequence` until it covers the captured prefix **through the existing publisher**, before imposing the tiny quota. Do not call acknowledge/compact manually to invent progress, enlarge the quota solely to hide failure, or change Core limits/semantics. Burst size and reserved rows may still require separate examination; current evidence cannot select a cause.

`test_agent_recovery_isolation.py:82` intentionally injects unavailable or hung history into only `subject`; it uses bounded `eventually` predicates, a `finally` that disables the fault/releases the barrier, and then three retained lifecycles. The exact failing assertion/trace is still pending. Do not classify that failure as the settings-pin issue or the structured-work factory issue without evidence. Recovery scheduling, archival policy and persistent lease state remain distinct proof layers.

## Safe next sequence

Wait for the original shards to finish/terminate with their retained statuses and hashes. Obtain the already planned bounded first-failure report. Review the test-only patches above before changing inputs. Re-run only affected fixture families in the qualified prefix with finite outer deadlines and exact owned-process cleanup. Preserve all antecedent failures, avoid any new native/provider campaign, and leave the immutable package and Core untouched.
