# Explicit Connector installation observation — 2026-10-02

Connector code commit `8ff791c` adds `executor probe` for an explicitly selected
Server executor, adapter, candidate reference and displayed inventory revision.
Discovery remains passive. The explicit command delegates the contained, sealed
version observation to Core and retains no runtime authority or provider secret.

Schema 13 retains up to 64 observations per executor. Reuse requires identical
complete passive candidate evidence, Core version and platform. The command
revalidates physical discovery scope, current registration and candidate bytes
before committing. Drift/failure cannot publish a successful observation.
Discovery reconfiguration clears retained observations. Older state migrates
without observation authority; older clients refuse the new schema.

Configured CLI discovery, daemon publication, workspace realization and execution
selection now use the same byte-bound observations. The daemon detects the changed
executor record and reconciles its control connection before publication. The
probe response explicitly says `publication_pending=true` and
`runtime_authorized=false`. Operator approval, grants, leases and Core launch
qualification remain separate. Probe before binding: a changed inventory revision
requires an explicit fresh realization/binding rather than silently mutating
approved consent.

## Evidence and limits

- Source selection: 198 tests passed across observation, configuration, onboarding,
  daemon, runtime admission and schema migrations. The initial run's eight fixture
  signature errors are retained; fixtures now explicitly accept the observation
  argument rather than bypassing the productive path.
- Complete installed Connector run: 693 passed, two skips and two packaging setup
  errors, 323.02 seconds. All 76 Connector package files matched the wheel and no
  monitored inputs changed. The two errors were absence of the declared `build`
  test dependency, not application failures; the original report remains FAIL.
- Both packaging cases passed separately in a new 26-package environment with
  the declared `[test]` extra. The cases built the wheel, installed it with the
  exact vendored Core into another clean venv and verified CLI/import/metadata.
  Dependency check passed. This is not the final offline M13 proof.
- The two retained skips are the historical lab peer's incomplete start contract
  and a non-Windows-only shim case. Neither is counted as acceptance evidence.
- Installed real CLI probes on Windows observed Codex 0.159.0 and Claude Code
  2.1.282 from NOT_PROBED to READY_FOR_RUNTIME with no qualification override.
  Stale selection was refused. These used an explicitly seeded local registration
  fixture, no real Server registration, no daemon publication and no native
  runtime opening. They are provider-observation evidence, not multi-host proof.
- Installed Nexus integration: 54 passed in 443.41 seconds with unchanged inputs.
  Coverage includes public onboarding/replacement CLI, real HTTP/WSS transport
  with synthetic native peers, binding approval and workspace eligibility. The
  three installed package trees matched their wheels.

See [Connector campaign](evidence/installation-observation/connector-installed/campaign.json),
[packaging results](evidence/installation-observation/packaging.xml),
[Codex](evidence/installation-observation/real-codex-probe.json),
[Claude](evidence/installation-observation/real-claude-probe.json) and
[Nexus integration](evidence/installation-observation/nexus-installed/campaign.json).
The campaign scripts and initial/source reports are retained alongside them.

Connector wheel SHA-256:
`0a7c6fd061be2624a39c3574005c50a0d4b68daf8dcdfb95fa4f982cd21869c9`.
Core remains the identical 0.2.53.dev0 wheel,
`cc873031378793d374a9bbc00572c7a525f99c4246324a941713d866cc62c6b1`;
all 95 installed Core files were checked again. Nexus integration reused the
already verified `bcf84f19264fe4233507cca9bb2b5ad0385c7c3dfb59a726afec63d9b67c4af8`
Nexus wheel because its application code did not change.

The Connector README follow-up `e235e3b` replaces the obsolete connect/start
quickstart, R3 transport description and initial-turn limitation. Five actual
installed help commands were checked. This follow-up changes documentation only;
the development wheel above was built at `8ff791c` and does not contain the later
README metadata. The final M13 build must include that correction.

Remaining work: embedded Server qualification API/UI, complete remote UI journey,
operator delegation, inventory refresh, independent hosts and final platform/fault
acceptance. Latest CI is not yet terminal. No G0–G3 gate or final freeze is claimed.
