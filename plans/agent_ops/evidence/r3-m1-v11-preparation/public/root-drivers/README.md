# v11 root drivers with one operator bootstrap

This is a new source-only candidate. The seven-driver freeze and its 51-case
qualification at `../m1-v11-driver-candidate-r3pnub4c` remain intact. Five runtime
driver bodies are unchanged. `driver_common.py` adds the eighth required pin and
one finite selection; `invoke.py` maps that selection to the new pinned helper.
The v10 artifacts and historical accounting remain unchanged.

Invocation is `invoke.py <the four required proposal/receipt arguments>
operator_bootstrap once`. Run only after the local setup, useful work and
continuation have settled, with the existing controller and Nexus owner ready,
before remote planning/transfer. All eight self-pins, exact final proposal digest,
revision 11 receipt, installed interpreter prefix, product payloads, native binary
and bundle pins are mandatory. The root creates the new technical receipt binding
the final proposal to the human authorization already received. This preparation
creates no receipt and does not imply the user personally approved a SHA string.

The helper uses only the proposal's own loopback Server and operator home. It
requires a fresh unconfigured local account, creates one generated password in
memory, durably reserves the single account POST, then obtains the existing
monitor's fresh effect grant immediately before dispatch. A lost response permits
only GET reconciliation and the same original in-memory password. A separate
exclusive reservation precedes the login grant. The canonical CLI receives the
password only over stdin and owns its normal protected vault namespace. Login
and status must report the exact profile, origin and historical canonical Server
ID. No personal credential is read by this driver.

`transfer_with_monitor` is reused unchanged: producer means account POST and
consumer means canonical login. Its owner thread polls the existing controller,
reattached historical work and setup accounting; the fresh nonproductive deadline
is at most 120 seconds. No model reservation or independent token counter is
introduced. CLI stdout is parsed in memory, stderr is discarded, and only a
closed nonsecret result is published. The worker and CLI process remain retained
until they exit; OS/process stalls are not claimed to be atomically bounded.
After a fault and worker drain, only the existing canonical Nexus normal-stop
wrapper may run, once. There is no force, login replay, password rotation or
second account POST. Closure still requires the existing independent cleanup
proofs; operator success alone never proves service exit or M1 acceptance.

Offline qualification: 78 unique cases = the prior 51 plus 27 operator cases.
Intermediate 69/78 runs are retained, not added to the total. Effects are fakes:
no real service, provider, account, OS vault, private database or authorization
was used. The actual pure monitor module is exercised for concurrent accounting,
ordered gates and a historical-usage fence closing before login. HTTP and Popen
are simulated, including response loss, exhausted gate, identity mismatch,
noncanonical origins, consumed reservations, stdin-only login and controller
attachment/normal-stop lifecycle. Compile-only and targeted Ruff checks passed.

Run command (Nexus cwd):

```
rtk proxy .venv/Scripts/python.exe -I -B C:/Users/jpamb/AppData/Local/Temp/m1-v11-operator-candidate-sqp53mdk/run_pure_tests.py
rtk proxy ruff check C:/Users/jpamb/AppData/Local/Temp/m1-v11-operator-candidate-sqp53mdk --select E9,F63,F7,F82
```

The runner uses isolated Nexus venv Python, explicitly inserts this candidate's
source directory, and uses only synthetic fixtures. The final runner refuses to
overwrite its `tests-run-003` history. Runtime awaits final bundle integration and
root review; these tests do not execute or close M1.
