# SI-018 exact live ownership proof in Core

Core 0.0.16 is on `feature/v0.0.16` at `30f349b293fd8d4458dee0267c04aaf3eda132af`. The prior 0.0.15 wheel and branch keep their existing artifact identity. The new read-only Core method is for a trusted host that already has the exact R4 scope and owner channel. It compares the active Core binding with the established opening operation, native session, stream epoch, adapter, durable receipt and slot. It checks the recorded process birth against both the bound process handle and an OS observation, then rechecks the current binding and the persisted lease before returning evidence.

The result identifies the owner boot, channel generation, session generation and process birth separately. A presenter will use its own scoped authorization and revalidate ownership at each effect. There is no change to the R4 bundle, journal schema, presentation transport, or native writer.

## Evidence

The final Core suite passed 102 focused tests covering runtime leases, resource release, native action ownership, process birth and session claims. The new synthetic case verifies refusal for missing or different birth, changed target fields, stale connection or generation, stale durable lease, and expiry during the OS observation. The positive proof opens one synthetic session and issues no native control. Both generated contract checks passed. Both 0.0.16 archives passed strict Twine checks. The three packaged source entries matched their worktree bytes, and the public types and method imported from the built wheel. Wheel SHA-256 `fd7d598a83a4586be4bd02a057cd785593dc44dcd00d304dc4797309f406c8a7`.

Consumer integration and live attach proof remain pending. The existing consumers still use Core 0.0.15 at this milestone. Any subsequent pin can roll back to that wheel before a presenter capability is enabled.
