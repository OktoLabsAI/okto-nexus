# Isolated protected-terminal preparation

Status: **synthetic qualification passed**, not a remote setup or campaign execution.

The final run (`run-006/qualification.json`) contains four cases. The ordinary
synthetic transfer and a transfer through the installed Nexus
`remote_setup_io.material_sink(False)` and Connector `import_flow.read_secret_stdin()`
passed. Both producer streams and input were genuine TTYs, and the associated
console window was not visible. The exact fictitious material was compared
inside the worker after stdin delivery; neither the material nor its digest is
part of any public result. Ambiguous material and an expired producer deadline
refused delivery and never started the consumer. Every case recorded zero active
processes in its exact owned Job after cleanup.

No Nexus/Connector CLI, HTTP request, service, provider, account, vault read/write,
or real credential was used. The two installed functions are called directly by
benign Python scripts. The Connector parser validates shape, not authentication.
The Nexus JSON-mode sink was also confirmed unavailable; the TTY check is not
patched or bypassed.

## API and ownership

Load the frozen `protected_pty.py` from its original directory. Call:

```python
transfer_once(producer_argv=public_absolute_argv,
              consumer_argv=public_absolute_argv,
              env=explicit_sanitized_environment,
              consumer_env=explicit_sanitized_consumer_environment,
              cwd=owned_temporary_directory,
              timeout_seconds=120,
              synthetic_probe=False)
```

The module does not authorize execution or validate proposal receipts. The caller
must validate the final proposal, approval, package/input hashes, exact arguments,
and ownership before invoking it. `synthetic_probe=True` is exclusively for these
test producers and sends an extra benign `go` line; it must not be used for a real
CLI. No input is sent to a production producer by the normal mode.

The owner starts a hidden base-Python worker, assigns it to its exact named Job,
verifies membership, then writes the gate message. Only after receiving that
message can the worker create its ConPTY producer. Producer and consumer PID and
birth time are captured and exact Job membership is checked. The worker retains
no query Job handle across waits. Low-level `winpty.PTY` is used instead of the
library's TCP-based `PtyProcess` wrapper. Raw PTY output is bounded and kept only
in worker memory, with no terminal transcript or raw exception text emitted.

The consumer receives a newline-terminated key through stdin. Its stdout/stderr
remain private in memory; any echo of the material refuses success. The helper
does not return consumer output. There is no retry or recovery of a lost key.
Python immutable memory is not claimed to be securely erased.

`consumer_env` is optional and defaults to `env`. The final qualification uses a
separate consumer environment with `OKTO_NEXUS_CONNECTER_DAEMON_FG=1`; both producer
scripts assert that flag is absent, and both consumer scripts assert its value is
`1`. The negative cases never start their consumer. The recorded environment flag
means it was supplied, not that an unstarted consumer observed it. This proves
environment separation, not the behavior of the real daemon-start path.

The outer owner has an operational timeout and only retained child handles or
the exact owned Job may be terminated. It does not enumerate or kill arbitrary
processes. Job membership includes all descendants, with no breakaway. A false
`forced_owned_cleanup` means the outer `TerminateJobObject` path was not used;
PTY teardown can still terminate a timed-out synthetic producer. This is not a
claim of graceful completion or a hard real-time OS bound.

## Integration boundary still pending

This Job may contain only disposable auxiliary CLIs, never a service or harness
whose continued life is required. Connector `connect --setup-receipt` eventually
calls `manager.start`; its already-ready path reuses the owner, but a prior status
observation is not an atomic guarantee that no start/restart will happen later.
The existing `OKTO_NEXUS_CONNECTER_DAEMON_FG=1` guard can refuse the direct fallback,
but its remaining Scheduler path and approved action scope must be reviewed by
the campaign owner. The helper itself does not resolve that race. It is not authorized to kill a
service, and this qualification does not establish compatibility with the full
remote `connect` lifecycle. The execution bundle must settle that boundary and
pin this helper and its dependency before actual use. No real CLI ran here.

The helper currently resolves the dependency relative to its original directory:
`venv/Lib/site-packages`. Copying only the helper into another bundle does not
install that dependency. Preserve the exact original path or explicitly prepare
and verify the dependency in the destination before freezing a future bundle.

## Reproduction and provenance

Use a new output directory for each synthetic run:

```powershell
rtk proxy C:/Python313/python.exe -I C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/qualify.py new-synthetic-run
```

The isolated dependency is the official CPython 3.13 Windows amd64 wheel
`pywinpty==3.0.3`, SHA256
`9c91dbb026050c77bdcef964e63a4f10f01a639113c4d3658332614544c467ab`.
It was installed only in this Temp venv, without dependencies or global changes.
`dependency-proof.json` compares its package payloads against the wheel and
records exact installed function source bytes used by the final case. The latter
is a focused input record; the broader three-product package qualification belongs
to the separately retained host environment proof.

Sources: [PyPI release](https://pypi.org/project/pywinpty/3.0.3/),
[official source tag](https://github.com/andfoy/pywinpty/tree/v3.0.3),
[official wrapper implementation](https://github.com/andfoy/pywinpty/blob/v3.0.3/winpty/ptyprocess.py),
[Microsoft pseudoconsole documentation](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session).

Runs 001–003 remain failed preparation attempts, with their sanitized observations
retained. Run 002 located unsupported ConPTY `cancel_io`; run 003 located EOF
raised by `read` after producer exit. Run 001's exact underlying failure was not
localized. Run 004 passed the initial three synthetic cases. The corresponding
first-success helper snapshot is retained; no claim is made that unavailable
earlier source snapshots were recovered. Run 005 retested the final owner-handle
change and added the installed-function case. Run 006 repeats the four cases with
the final separate consumer environment. Historical evidence is unchanged, and
the first public qualification is copied under `history-public-v1` in the final
curation.

The public manifest is an explicit allowlist. It excludes environments, synthetic
homes, pycache, raw output, keys, credentials, and the dependency wheel itself.
