# SQLite writer progress and installed acceptance — October 2, 2026

The connection factory now admits waiting write transactions in FIFO order.
A producer cannot repeatedly reacquire its local writer slot ahead of an already
waiting heartbeat or dispatcher. Queue waiting consumes the existing configured
SQLite admission budget; the remaining budget is passed to `BEGIN IMMEDIATE`.
There is no automatic transaction replay. Read snapshots bypass the queue.
Connection closure releases the slot after success, rollback, failed BEGIN,
failed commit and an exception in the pre-write hook.

This ordering belongs to one connection factory. SQLite still coordinates other
factories/processes; this change does not promise cross-process FIFO scheduling
or availability when storage remains unavailable.

## Corrected load fixture assumptions

The previous installed Linux run lost its reconciled channel during repeated
identity writes. The first source run with FIFO admission had no logged storage
failure but still failed the arbitrary `baseline + 4` thread assertion. Captured
stacks showed normal lazy expansion of the default executor: fifteen additional
workers were idle and one was reading the embedded publication page. The test
now checks the actual executor identity/capacity and its worker membership,
while retaining a separate bound on new threads outside that pool. It still
checks indexed lookup, 4,096 cache entries and bounded traced memory.

The first installed Windows campaign passed 41 checks, then failed load dispatch.
The retained database proves its initial 120-second lease expired just before
dispatch; unsent operations were correctly rejected for missing an applied
lease. The synthetic peer now periodically observes/publishes inventory through
authenticated HTTP and renews/applies its lease through the real WSS route. A
sequential request replay verifies the ACK committed without creating another
lease. No timestamp, freshness anchor or TTL is forced. The final test preserves
the 100,000 identities, 500-identity transactions, flooded executor, reserved
control capacity, second executor and withheld synthetic peer receipts.

## Verification

The same fresh development wheel was installed on Windows/Python 3.13.1 and
WSL Linux/Python 3.12.13. The runners used isolated Python outside the checkout,
verified all three package trees against their pinned wheels and recorded no
changed campaign inputs.

| Campaign | Result | Scope |
|---|---|---|
| Windows source writer checks | 19 passed | FIFO, expiry, readers, cleanup, shared timeout and error contracts |
| Windows source regression | 22 passed | Ownership, external writers, capture/projection, dispatch and link failures |
| Linux installed regression | 42 passed | Same areas plus load, before periodic fixture lease maintenance |
| Windows installed regression | 41 passed, 1 failed | Retained expired-lease failure described above |
| Windows final installed | 24 passed, 199.11 s | Final load fixture, NS15.05, provider vault and NS09 lease cases |
| Linux final installed | 23 passed, 1 skipped, 166.49 s | Same cases; Windows Credential Manager integration skipped on Linux |

Campaigns overlap; these counts must not be added into a unique-case total.
The final Windows load took 148.14 s and reached lease serial 6; Linux took
92.06 s and reached serial 4. Both authenticated 100,000 identities, rejected 20
overflow submissions while dispatch progressed, and sent the control operation
in under 0.46 s. These measurements describe one physical computer with WSL and
synthetic native peers, not independent hosts or provider qualification.

- [Windows final campaign](evidence/ci-writer-fairness/windows-final/campaign.json)
  and [JUnit/measurements](evidence/ci-writer-fairness/windows-final/tests.xml).
- [Linux final campaign](evidence/ci-writer-fairness/linux-final/campaign.json)
  and [JUnit/measurements](evidence/ci-writer-fairness/linux-final/tests.xml).
- [Linux regression](evidence/ci-writer-fairness/linux-regression/campaign.json).
- [Windows failure](evidence/ci-writer-fairness/windows-before-renewal/tests.xml)
  and [persisted lease/error evidence](evidence/ci-writer-fairness/windows-expired-lease.json).
- [Earlier installed channel failure](evidence/ci-writer-fairness/before-installed/tests.xml)
  and [source pool stacks](evidence/ci-writer-fairness/nexus-writer-fairness-source-linux.xml).

## NS15.05 and hosted reconciliation

Hosted `43aa8de` Linux cells completed with 3,512/3,511/3,511 passes for Python
3.11/3.12/3.13 respectively. All failed the documentation audit because its
in-process entry consumed pytest arguments. Python 3.12 also hit the thread
heuristic; Python 3.13 hit the overwritten first host failure already corrected
in `bd3e204`. The audit now accepts explicit arguments and its test writes into
`tmp_path`, preserving historical/user evidence. Final installed NS15.05 passed
on both systems; the standalone CLI audit also passed with a separate
[report](evidence/ci-writer-fairness/docs-cli.json).

Connector `37726bd` completed four successful cells, but Windows 3.12 and 3.13
still failed observation timeouts in five cases. Their cause remains unresolved;
no timeout was increased. See the [hosted follow-up](evidence/ci-writer-fairness/hosted-follow-up.json).

## Artifacts and remaining acceptance

- Nexus wheel SHA-256: `bb2684dd29b69dd42fab7a6ddc9c7de2cbd9c755fda4ed24095aa953dd9827c5`.
- Nexus sdist SHA-256: `f5451a558b0c37f5a3e1188b8bf01debec43f45327e9c1327ffb89c20bcc87df`.
- [Build manifest](evidence/ci-writer-fairness/build-manifest.json) records the
  parent commit plus exact source hashes; Core/Connector wheels are unchanged.

This is a development artifact, not the M13 freeze. Final hosted regression,
Connector timing diagnosis, dashboard completion, persistent-store failure
recovery and independent-host/platform/provider acceptance remain open.
NS15.05 remains partial and G0–G3 remain open.
