# Protected terminal helper — cooperative revision 3

**Seven synthetic cases passed. No product CLI, service, provider, account or real
credential was used.** This revision replaces the previous helper's invalid
assumption that the one-shot producer can exit before the consumer starts.

The worker now starts the consumer exactly once when it observes one complete
canonical header/key/footer block, while continuing to drain the producer's PTY.
One owned I/O thread writes the key to consumer stdin and receives its outputs
privately. Success requires producer and consumer exit zero, completed consumer
I/O, no subsequent material ambiguity, and an empty Job without forced cleanup.
There is no retry or second delivery.

The finite qualification (`run-001/qualification.json`) covers:

* Cooperative producer: it cannot exit until its consumer writes a public
  completion bit. The consumer starts while the producer is alive; both exit0.
* Ambiguity before delivery: no consumer, no delivery attempt or completion bit.
* Ambiguity after receipt: one consumer and a delivery attempt; `UNCONFIRMED`,
  `possible_consumer_effect=true`. It never reports zero delivery or retries.
* Producer deadline before material: no consumer or delivery attempt.
* Consumer deadline after receipt: `UNCONFIRMED`, possible consumer effect; only
  the exact owned synthetic Job was terminated and its active count became zero.
* Consumer exit9 after receipt: refused, possible consumer effect, no retry.
* Installed IO functions: the real Nexus `material_sink(False)` runs under three
  genuine TTY streams and its JSON-mode sink remains unavailable; the real
  Connector `read_secret_stdin()` reads the fictitious value. The producer still
  waits for the consumer completion bit. Both exit0 and the Job is empty.

All seven cases observe an empty Job after cleanup. The two positive cases prove
three TTYs, no visible console window, matching fictitious material across the
private stdin boundary and absence of that material from their synthetic files.
Completion markers contain only fixed booleans, never keys or key digests. The
digest used to compare material remains in a private pipe and worker memory.

`possible_effect` is conservative once the producer has started: a real producer
could already have created an identity even when no consumer was started.
`possible_consumer_effect`, `consumer_started`, `consumer_start_count`, and
`delivery_attempted` separately describe the delivery boundary. Unknown worker
failure does not establish absence of effects. `consumer_io_completed=false`
means completion was not confirmed before the failure. Python memory is not
claimed to be securely erased.

## Frozen interface and paths

The executable source is the original `revision-3/protected_pty.py`, together with
its adjacent `owned_job.py`. Its public copy is for review and evidence. It loads
the pinned dependency from the parent's `venv/Lib/site-packages` directory. Do not
move the module without preparing and pinning that dependency relationship.

```python
transfer_once(producer_argv=public_absolute_argv,
              consumer_argv=public_absolute_argv,
              env=producer_environment,
              consumer_env=consumer_environment,
              cwd=owned_directory, timeout_seconds=120,
              synthetic_probe=False)
```

`consumer_env` defaults to `env` when omitted. The qualification explicitly puts
`OKTO_NEXUS_CONNECTER_DAEMON_FG=1` only in the consumer environment; its fixtures
assert that separation. `synthetic_probe=True` sends a `go` line only to the
benign fixture and must never be used with a product producer.

The owner assigns the hidden worker to an exact named Job before releasing its
stdin gate. The worker then creates the ConPTY producer. All descendant processes
are contained without breakaway; PID/birth and exact membership are checked.
The parent keeps the Job lifetime handle. Worker query handles are short-lived.
Raw terminal output and consumer stdout/stderr never leave worker memory.
Timeouts are operational bounds, not hard real-time OS guarantees. A failed
consumer I/O thread cannot escape its worker process or the exact owned Job.

Only auxiliary CLIs and their finite probes may belong to this Job. It must not
own a productive session or a service that is supposed to persist. The Connector
`connect` path may request `manager.start`; its fallback/Scheduler behavior and
any allowed implicit ensure/start are separate proposal/ownership conditions.
This helper neither authorizes those effects nor verifies external service state.
No product CLI or Scheduler operation was executed to establish this boundary.

## Evidence and reproduction

Run with a new synthetic output directory:

```powershell
rtk proxy C:/Python313/python.exe -I C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-3/qualify.py new-run
```

The dependency remains official `pywinpty==3.0.3`, Windows CPython3.13 wheel SHA256
`9c91dbb026050c77bdcef964e63a4f10f01a639113c4d3658332614544c467ab`.
Twelve wheel package payloads equal the isolated installation. The installed
product function inputs are rechecked against the previous focused proof. This
is not a replacement for the separately qualified full host-package proof.

Sources: [official release](https://pypi.org/project/pywinpty/3.0.3/),
[official code](https://github.com/andfoy/pywinpty/tree/v3.0.3),
[Microsoft ConPTY documentation](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session).

`history-public-v2` preserves the previous 62-payload curation and its manifest,
including the earlier preparation failures and narrower passing runs. Those old
passes do not qualify the real producer/consumer dependency. The new diff and
seven-case report qualify this correction only. Public copying is restricted by
the manifest: no synthetic homes, raw terminal output, keys, environments, wheel
binary or pycache are copied.
