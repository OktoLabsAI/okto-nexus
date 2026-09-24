# Work acceptance and remaining exact stimuli

Parent d1e300c. Completed scoped WORK01–11 evidence; full plan gate remains NOT PASSED. Production code is unchanged in this unit.

New tests in `tests/test_runtime_work_acceptance.py` use the production HTTP app/MCP mount and disposable stores. Competitive claims use three authenticated identities and endpoint-scoped grants. All candidates can observe the open offer without payload. Concurrent REST/MCP claims yield one winner, one charged execution grant and one native dispatch. Winner reads its permitted payload/runtime; losing identities cannot read the private payload, winning execution binding or operation on either runtime surface. Existing multi-endpoint competition additionally proves that another endpoint of the same identity does not duplicate work; same logical identity is not falsely treated as a privacy boundary.

The interrupt cases use a real owned Codex protocol pipe. The peer writes its RPC acknowledgement, then waits on a bounded fixture gate before emitting the correlated native interrupted terminal. Before release, the persisted interrupt command is `verb=interrupt,state=SENT_UNCONFIRMED,expected_operation_id=<work>` and the handoff remains CLAIMED without result. This is the existing explicit representation of the logical INTERRUPT_REQUESTED state; no new handoff terminal state or false durable ACK is invented. After release, one interrupted result is durable, while the handoff still requires its canonical work decision. Both REST and MCP controls are exercised.

The restricted Codex profile has managed_work/approvals disabled and verified conversation capability. Managed claim is rejected without changing the handoff, creating an outbox executor or charging its grant. A conflicting required approval cannot overwrite that profile. Two subsequent native-pipe conversations succeed. Additional Claude stream cases reject sandbox/approval-policy launch options this adapter does not implement, preserve the existing profile/revision and then complete a compatible native-pipe conversation. This does not claim Claude implements the rejected sandbox contract.

## Preparation and scope

Initial three interrupt/conversation cases:3 PASS Windows. First competitive extension:3 PASS1 FAIL, because the test incorrectly expected execute_work alone to grant runtime read. The fixture now grants each candidate read only on its own endpoint and verifies positive visibility before competition. No security rule was weakened and this is not a product RED/fix claim.

The main selection completed47 PASS Windows154.40s and47 PASS Linux178.70s. It ran the four new initial cases plus existing managed dispatch, structured work results and profile requirement tests. The new file was then extended by two sandbox/approval-policy cases; the final generation selection reruns the whole six-case file. Bootstrap/approval/input and generation/recovery selections are complementary, not replacements for the final full suite. All external peers here are synthetic; installed-provider evidence remains separate. Do not count overlapping test nodes twice as a unique-suite total.

## Commands

```text
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_work_acceptance.py -q --junitxml=.git/pr34-evidence/work-acceptance-initial.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_work_acceptance.py -q --junitxml=.git/pr34-evidence/work-acceptance-windows.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_work_acceptance.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_work_results.py tests/test_runtime_profile_requirements.py -q --junitxml=.git/pr34-evidence/work-acceptance-expanded-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_work_acceptance.py tests/test_runtime_handoff_dispatch.py tests/test_runtime_work_results.py tests/test_runtime_profile_requirements.py -q --junitxml=.git/pr34-evidence/work-acceptance-expanded-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_bootstrap.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py -q --junitxml=.git/pr34-evidence/work-approval-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_bootstrap.py tests/test_runtime_native_approvals.py tests/test_runtime_claude_approvals.py tests/test_runtime_native_inputs.py -q --junitxml=.git/pr34-evidence/work-approval-linux.xml
rtk proxy .venv/Scripts/python.exe -m pytest tests/test_runtime_work_acceptance.py tests/test_runtime_handoff_epochs.py tests/test_runtime_handoff_recovery.py -q --junitxml=.git/pr34-evidence/work-generation-windows.xml
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest tests/test_runtime_work_acceptance.py tests/test_runtime_handoff_epochs.py tests/test_runtime_handoff_recovery.py -q --junitxml=.git/pr34-evidence/work-generation-linux.xml
rtk proxy ruff check tests/test_runtime_work_acceptance.py
```

The evidence index will map each requirement to exact passing parameterized nodes on both platforms, retaining prior coverage limitations. WORK-12 attach/external authenticated completion and the native attach gate are not qualified by these tests. No P12/final gate promotion.

## Final verification

All executions are terminal; no running test handles remain. Main selection Windows75782:47 PASS154.40s; Linux68372:47 PASS178.70s. Approval/bootstrap selection Windows96967:46 PASS197.38s; Linux79709:46 PASS216.52s. Final generation/new-test selection Windows43945:25 PASS101.96s; Linux49823:25 PASS116.82s. Each generation run emitted one existing Starlette TestClient deprecation warning. Ruff and git diff --check PASS.

These selections cover114 distinct parameterized test nodes per platform (118 executions with four intentionally repeated cases). The [acceptance index](evidence/p12-work-acceptance-index.json) resolves every required base name to actual PASS nodes on both platforms, records exact parent/new-test hashes and links sanitized per-node manifests. New final-file cases come from the generation run, not the earlier pre-extension file hash. Existing source/test bodies remain at the parent revision.

| Requirement | Verified behavior |
|---|---|
| WORK01–02 | Competitive single execution and offer/loser privacy with positive winner access |
| WORK03 | Claim/notification coalescence and idempotent single dispatch |
| WORK04 | Canonical bootstrap identity/profile/purpose, no authority fields from payload |
| WORK05–06 | Native turn end does not complete work; explicit complete/reject/verification uses core authority |
| WORK07 | Explicit uncertain-work recovery advances claim epoch; late old result stays durable without completing new work |
| WORK08 | Delayed native interrupt terminal; durable request is not completed interruption |
| WORK09–10 | Operator-only native allow/deny, repeated/conflicting/late decisions and request reuse fences |
| WORK11 | Unsupported work/input/sandbox contracts rejected; compatible conversation preserved |

WORK12 stays NOT_RUN for its complete attach-plus-authenticated-external-channel stimulus. No claim of a new attach ACK/completion channel, native-provider approval qualification or completed P12 phase. Next: lifecycle active-turn SIGTERM and fragmented UTF-8/pipe-pressure acceptance, remaining matrix joins and final full release gates.
