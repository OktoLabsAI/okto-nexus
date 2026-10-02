# NS15.05 operational reconciliation — 2026-10-02

Connector `768a688` reconciles the runbook, architecture and threat model with the
implemented R4 path. Follow-up `e09fa21` clarifies the README's runtime/read surface.
Historical increment claims no longer describe R4 as disabled in the current
architecture. Management identity, control tickets, native capabilities, applied
leases and local probe consent are documented as separate authorities.

Concrete operational corrections:

- Replace legacy connect/start instructions with canonical identity import,
  registration, explicit selection, realization and reviewed binding.
- Put global `--json` before `doctor`; distinguish network diagnosis from the
  explicit contained installation-version probe.
- Remove a nonexistent standalone reconciliation command and invalid
  `bind remove --keep-config=false` syntax. Preserve the real `mcp-config remove`
  command with explicit file/entry ownership scope.
- Stop describing legacy logs as a complete R4 viewer or local alias removal as
  canonical revocation. Document retained operation/session queries.
- Correct journal-full and rollback instructions: no deletion of uncertain
  history, no invented general compaction command and no promise that an older
  binary can read newer state.

The `doctor` product defect was also corrected: its `contract` check now verifies
the executable R4 bundle/revision, while `legacy_contract` is explicitly separate.
Invalid, missing or disabled bundles report failure. A verified bundle does not
claim provider qualification, binding approval or an applied execution lease.

## Verification

Eight directed tests passed from source and eight from the installed wheel.
They cover the current, disabled, missing and invalid R4 bundle, unsupported
platform diagnosis, and fresh CLI discovery/doctor behavior.

The installed Connector parser accepted all 34 command examples across the
README and operational documents. Each example's real installed `--help` command
also passed; 12 local links were checked. Examples were parsed, not dispatched:
the audit did not import credentials, start runtimes or mutate remote state.
See [audit](evidence/ns15-operational/connector-docs.json) and
[installed tests](evidence/ns15-operational/doctor-installed.xml).

The Nexus installed guide audit passed seven help commands, 14 declared routes
against installed router definitions and five links. The audit now accepts an
explicit output path; the pre-existing `ns15-05-docs.json` was preserved. Route
presence is supporting evidence, not proof of each operational scenario.
See [Nexus audit](evidence/ns15-operational/nexus-docs.json).

Current Connector development wheel SHA-256:
`508eaf654ec34e8fa8ff513d3c78c46d86cfc0555475cd91a721c9458b511bea`.
All 76 application package files matched the tested wheel byte-for-byte after
the final README refinement; only METADATA/RECORD changed in that refinement.
Compared with the prior 693-pass full-suite artifact, the only application file
changed is `doctor.py`, covered by the directed installed tests above. Prior
runtime/onboarding evidence is reused only for its unchanged application files;
this is not a claim of a fresh complete suite or latest six-cell CI.
See [artifact comparison](evidence/ns15-operational/artifact.json).

Nexus adopts this hash-pinned Connector test artifact. The installed smoke verified
all three package trees against their exact wheels; Nexus/Core application code
did not change in this increment. The new Connector artifact includes the README
corrections missing from the preceding `8ff791c` wheel.

## CI and remaining acceptance

Run `36965980734` at Nexus `abd402a` was confirmed completed/cancelled after an
explicit redundancy cancellation. `git diff 58b38b5 abd402a -- src tests vendor
pyproject.toml uv.lock README.md .github` was empty. The `58b38b5` run was preserved;
the cancellation was not a timeout retry and supplies no passing evidence.

Correction after inspecting the scenario manifests and JUnit reports: TN-38,
TN-39 and TN-40 already have passing evidence at their declared layers on the
October 1 artifact tuple (Core .51). They do not need implementation from scratch;
final-artifact regression remains required. The earlier remaining-work statement
overlooked those records. See [MCP and ledger reconciliation](M12_NS15_05_MCP_RECONCILIATION.md).
NS15.05 remains open for complete dashboard/dependency acceptance and final
artifact verification. Embedded qualification, operator delegation,
inventory refresh, full UI, independent-host/fault/platform acceptance and final
M13 artifact freeze also remain open. No G0–G3 closure is claimed.
