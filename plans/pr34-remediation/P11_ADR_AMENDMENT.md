# P11 — amend ADR0004 to the accepted remediation

Parent `5c661fa`, feature/v0.2.0, 2026-09-23. Documentation only;
schema054/surface42/identity9 unchanged. Final gate NOT PASSED.

docs/design/0004-harness-integrations.md previously described implicit Agent
registration, an inherited LAN provider, Codex approval/sandbox bypass and
unrestricted notable-event messages. It now preserves decision IDs D1–D10 while
recording the accepted canonical identity/endpoint/session architecture, shared
authentication, scoped grants, approved profiles, serve ownership, durable
transport/journal, correlated private results, bounded causal relay and executable
handoffs. Four connector capabilities and platform limitations stay distinct.

The original remains in Git history. The amendment explicitly cites the supplied
contracts/source-traceability documents and does not attribute later design
decisions to the original review. Native versions and historical counts are not
recast as current verification. Effective probes, managed-claim recovery, UI,
backup/restore and P12/native acceptance remain pending.

Validation: Python pathlib/re checked all six relative links against the local
filesystem; PASS. Searches/assertions confirm removal of the old LAN address and
danger-full-access instructions. `rtk git diff --check`: PASS. No runtime behavior,
provider configuration, real model invocation or user store was changed.

The renewed full-suite inventory remains in progress. Command:
`rtk proxy .venv/Scripts/python.exe -m pytest -q --maxfail=10 --junitxml=plans/pr34-remediation/evidence/current-suite-inventory.xml`.
It started on the routing-migration worktree (subsequently committed5c661fa), before
the final exact VALIDATION_ERROR assertion was strengthened; that assertion was
separately verified1 PASS. No aggregate result is claimed while the process runs.
