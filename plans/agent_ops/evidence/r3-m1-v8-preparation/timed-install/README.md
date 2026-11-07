# BASE-06 preparation — not an installation or campaign acceptance

The new execution interpreter is
`C:/Users/jpamb/AppData/Local/Temp/m1-base06-install-g9ii2zhe/venv/Scripts/python.exe`.
Only 3,209 dependency files were copied, byte for byte, from the qualified
`m1-observation-hosts-ai03jk1l` environment. Its source was not changed. Nexus,
Connector, Core and their distribution metadata were excluded. The isolated
probe confirmed all three `find_spec` results are `None`; pip 24.3.1 and MCP
1.30.0 are available. There is no product installation, installation reservation,
real approval receipt, service, provider call or credential operation here.

`base06-contract.json` supplies the fixed paths and artifact hashes for the
final v8 proposal. `timed_install.py` accepts:

```text
<new-python> -I -B -X utf8 <timed_install.py>
  --proposal <final-v8-proposal>
  --expected-proposal-sha256 <reviewed-final-sha256>
  --approval-path <actual-user-approval-receipt>
  --approval-sha256 <reviewed-receipt-sha256>
  --execute
```

Without `--execute`, it only validates. Both modes require the separately
pinned approval receipt; this preparation does not create one. The gate checks
v8, the exact campaign root, policy and ancestry, the fixed target environment,
installer/requirements/dependency hashes and all three wheel pins. This is an
instrumentation gate over an externally reviewed receipt, not an independent
system for proving that a human approved a request.

Execution exclusively creates and fsyncs `installation-reserved.json` before
pip. Existing reservation/result/unknown files refuse another execution, even
if a previous file is incomplete. Pip installs the three exact existing wheels
offline, without dependencies, cache, prompts or bytecode compilation; hash
requirements are checked again by pip. No rollback, reinstall, uninstall or
automatic retry is attempted. Success produces `installation-result.json` only
after the 982 payloads match the wheels, imports resolve inside the new prefix
and `pip check` succeeds. A failure retains the reservation and attempts to
write `installation-unknown.json`; absence of that diagnostic does not remove
the reservation. A lost successful response can be inspected through the
completed result file without installing again.

The pip subprocess uses the actual `C:/Python313/python.exe` with CPython's
`__PYVENV_LAUNCHER__` set to the fixed new venv executable. A benign metadata
probe confirmed the virtualenv prefix and that the launched PID is the actual
child PID, avoiding the Windows redirector ambiguity. No product was imported
by that probe. Pip has a 180-second subprocess timeout; metadata/pip-check
probes have 30 seconds. Timeout or interruption leaves the installation
uncertain; no atomic rollback or hard filesystem latency guarantee is claimed.

The receipt stores monotonic nanoseconds and UTC at the installation start and
completion. BASE-06's later end must come from the first useful canonical result
observed on this same boot and campaign. Dependency copying, wheel creation,
downloads and waiting for approval are outside this prepared measurement. The
installation receipt alone does not demonstrate installation-to-useful-result
latency, nor does preparation demonstrate that the future installation passed.

Qualification: 27 synthetic gate/receipt tests passed with Popen and subprocess
run prohibited by the test fixture; no pip/network call occurred in them.
The tested source is preserved under `tested-before-lint`. Afterwards only an
unused `sys` import was removed from the installer; the finalizer lost an unused
import and an equivalent lambda became a function. No test behavior was changed.
All four final Python files pass Ruff. The earlier direct-interpreter probe ran
while dependency copying was incomplete and reported stderr; it is retained as
a preparation diagnostic, not a successful readiness proof. The final probe
completed with exit 0 and empty stderr.
