# Supervised runtime failure diagnostic — source and installed qualification

A scheduled service clears `launch_requested` when its runtime begins. Previously, if that owner later exited with known failure code 1, 2 or 3, a ready-but-inactive native task could be reported as simply stopped. Nexus and Connector now expose `SUPERVISOR_LAST_ATTEMPT_FAILED`, retain `state=unknown`, and direct the operator to inspect the task and stop explicitly before another launch. The diagnostic does not infer that the current launch or native retry budget is exhausted. Queued/running/unknown task states, success/status codes and the explicit-stop latch retain their existing meaning.

The committed changes affect only one production file and its test file per repository:

- Nexus: `d70f15cbe05c71c298d69ecae079bace422743aa`, branch `feature/v0.3.3`.
- Connector: `8400512601328e03191b03e0b6fba8943a09772c`, branch `feature/v0.0.12`.

Both commits were pushed and local HEAD matched the corresponding origin branch. Root reviewed the production/test diffs before the installed qualification and commits.

## Qualification and preserved failures

- Nexus source: **69 PASS** across service installation and service start tests. Before the product correction, the three new failure-code regressions failed because the observed state was `stopped`. That original execution produced no XML; its tool transcript reference `ee17c1` is retained in `qualification.json`, expressly as a transcript reference rather than a reconstructed execution receipt.
- Connector source: **41 PASS / 3 fixture failures**, preserved verbatim in `connector-source.xml`. The new diagnostic assertions passed, but the finite fake clock iterator remained patched during a later stop-latch file write and raised `StopIteration`. Restricting the fake-clock context fixed the fixture without changing product bytes; the three affected cases then **passed**, retained separately in `connector-delta-final.xml`.
- Installed wheels: **18 PASS / 74 deselected**, with product imports asserted under the new isolated environment's `site-packages`. Each host contributes nine cases: failed preownership observation (one), failure after runtime entry for exit codes 1/2/3 (three), and queued/running/unknown or native success/status-code discrimination (five). No broad suite was repeated during the host load.
- Ruff checks for E9/F63/F7/F82, scoped `git diff --check`, and the explicit public-artifact secret-pattern scan passed. The nine allowlisted artifacts were copied byte-for-byte; the original failing XML was not edited.

## Wheels and payload provenance

The artifacts were built directly from the repositories into `C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/wheels`, without a second source-tree copy. They were installed in that preparation's own environment. M1 wheels, receipts, homes and runtime state were not changed.

| Artifact | SHA-256 |
| --- | --- |
| `okto_nexus-0.3.3-py3-none-any.whl` | `3b81d80664a9744097bf89165f42f0977eb5194e65a9ef011455ab6ab6e9b3a6` |
| `okto_nexus_connector-0.0.12-py3-none-any.whl` | `87aad763ac4b35b973bfe2e63a76715f0ed6eb4196fbaad04a0a280997bb2bfd` |
| Unchanged Core `okto_nexus_connector_core-0.0.14-py3-none-any.whl` | `a05e4255254f9e96241890db1ac448fd228f4bb6868a112753de8cd667989325` |

The Nexus wheel includes committed heartbeat change `9379d207`. Source, wheel member and installed bytes were compared for four payloads: Nexus `service_manager/local.py`, Nexus HTTP `lock.py` and `app.py`, and Connector `daemon/lifecycle.py`. Exact payload hashes appear in the retained qualification. This is a payload provenance check for the heartbeat delta, **not an installed heartbeat test claim**; the 18 installed cases qualify only the supervisor diagnostic behavior described above.

The retained qualification SHA-256 is `0e0a353b744616bd93f204da1d2c86b4c1fcc2cce7c994ed168f39a903bd5628`; the originating nine-file public allowlist SHA-256 is `2e1e109b3afae6c0c8fdc2d213e355b68643ba12d34763f254c561f10a1317cd`.

## Scope remaining

No real task was installed, crashed, retried or stopped by this qualification. No provider authentication or model turn ran. No arbitrary NTSTATUS failure classification is claimed. SVC-T19 and SVC-T20 remain pending their separate disposable-service campaign; this evidence does not promote either scenario or any M1 acceptance. Ledgers were not changed by this curation.
