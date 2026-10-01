# Retained Server shutdown on signals

## Implementation

The serve entry point now uses RuntimeServer, a Uvicorn Server subclass whose signal handler schedules the existing ServerShutdownCoordinator. It does not set should_exit or force_exit while resources remain pending. Repeated signals reuse one observer and the coordinator's first deadline. The coordinator continues to close admission, retain ownership, recover and set should_exit after drain.

A signal during ASGI startup waits for the coordinator to be installed. A failed startup ends that observer without hanging. Uvicorn still installs and restores its signal handlers; handled signals are consumed rather than re-raised after drain. The earlier POSIX no-op SIGTERM handler is removed. No force-exit command is added by this increment.

## Evidence and scope

Four child-process tests invoke the actual serve entry point with installed packages and a disposable home. Each uses real HTTP, a real coordinator and embedded inventory, with passive discovery returning no candidates. Inventory release raises a technical storage error until the parent creates the restoration marker.

The child receives SIGINT or SIGTERM through Python signal.raise_signal, requested over its private stdin control pipe. Both signal-first and administrative-HTTP-first sequences are tested, followed by a second signal. Health and operator shutdown status remain available while pending. The fixed deadline is unchanged; restoring inventory release allows normal process exit code 0 and durable DISCONNECTED inventory state.

Two additional tests cover signals before coordinator initialization, successful startup and startup failure. Existing administrative shutdown tests still cover owned synthetic native recovery and separate CLI transport. These scopes are recorded separately: the signal child tests do not open actual provider processes.

See test_runs_20261001_server_signal.json for the installed artifact tuple and test counts. Source tests overlap installed coverage. Uvicorn behavior was checked against the installed 0.54.0 implementation.

## Remaining acceptance

Windows Python signal delivery is verified; external console control events and Linux external SIGINT/SIGTERM are not accepted by this campaign. The complete two-runtime late-open/stuck-close/release matrix, native-process-versus-durable-release projection, authorization-store outage, qualified explicit force-exit and platform/provider matrix remain pending. NS14.03 and all release gates remain open.

Core and Connector artifacts are unchanged. Earlier actual Pi/Codex/Claude results keep their original artifact scope. Preexisting modified UI assets are present in the wheel without UI acceptance.
