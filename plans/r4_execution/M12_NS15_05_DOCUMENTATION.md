# NS15.05 documentation cutover — October 1, 2026

Status: implementation in progress; normative scenario acceptance remains NOT_RUN.

The README now routes execution setup to `docs/harness-integrations/r4-operations.md`.
That guide describes embedded Core without the Connector application, remote
executor ownership, direct HTTP MCP, canonical binding/admission, capability
denials, uncertain outcomes and joint offline recovery. Old operator and admin
guides are explicitly legacy references; their stdio proxy guidance was removed.
The evidence index now points to R4 campaigns rather than claiming the previous
remediation release counts as current qualification.

MCP identity resource version 29 and surface revision 62 invalidate cached
guidance. Identity/auth descriptions and a runtime error no longer direct callers
to a stdio client. Dashboard source help now describes HTTP MCP and the actual
CLI help command. Historical evidence files remain historical records.

## Verification

- `audit_ns15_05_docs.py` ran with the previous NS15.04 installed campaign
  interpreter using `-I`: seven real CLI help commands exited zero; thirteen
  documented routes match imported installed route declarations; five local
  guide links exist and four adapter identifiers match Core. See
  `evidence/ns15-05-docs.json` for commands and source hashes. This checks command
  and route existence, not a full runtime workflow or final new wheel.
- Source regression: `tests/test_frente1_resources.py`, `tests/test_tools_surface.py`
  and `tests/test_surface_metrics.py`: 26 passed. JUnit:
  `evidence/ns15-05-resources.xml`. The first run had 25 passes and one stale
  resource-version assertion (messages expected 4, actual 5); messages/handoff
  expectations now reflect already-published version 5 and identity expects 29.
- Frontend TypeScript build passed. Production assets are built separately under
  the system temporary directory, preserving the preexisting worktree assets.

## Remaining required scope

Review the rest of active help/resources for legacy onboarding assumptions, then
exercise the normative documentation scenario against the packaged dashboard
and final installed artifacts. Current checks are supporting evidence and do not
close TR4-15-05. TN-38 requires 100,000 identities, TN-39 bounded cache/revocation
under churn, and TN-40 supported rollback preserving data/policies. Those are
separate acceptance scenarios, not implied by this document revision.

No G0–G3 gate or task dependency acceptance is promoted. Final package integration
must include the rebuilt dashboard; the preexisting static asset changes have
not been overwritten or included in this documentation commit.
