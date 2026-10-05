# Embedded installation version check

The dashboard now lets an operator explicitly select the exact local installation
and approve its contained version command before workspace preparation. Passive
discovery still does not execute or trust a candidate. The HTTP endpoint accepts
the published candidate reference/revision and adapter, never arbitrary command
arguments, paths or environment values. Runtime approval remains separate.

The embedded owner serializes discovery and probing, retains ownership after HTTP
cancellation, and waits for a pending probe during shutdown. Authority, executor
generation, inventory freshness and file identity are checked before/after the
probe. Core executes in a temporary directory without provider credentials.
Migration 098 retains up to 64 host-local observations tied to exact candidate
metadata, Core version and platform. Passive refresh/restart can reuse an exact
observation, but cannot reuse it after candidate/Core/platform drift.

An observation committed before publication failure can be republished without
another version command. Lost replies require inventory refresh and explicit
new consent before another check; repeated explicit POSTs are not an exactly-once
API. The UI resets consent and guards against late callbacks after unmount.

## Evidence and scope

- `evidence/local-check-installed-windows/`: 59 passed, including the new backend,
  real packaged Edge UI, local preparation, inventory, migration and NS15.05 audit.
- `evidence/local-check-installed-linux/`: 50 passed on WSL Linux, without browser
  tests. Both campaigns report PASS, exit 0 and `changed_inputs: []`.
- `evidence/local-check-reviewed-ui/`: 9 packaged Edge checks passed in 82.99 s,
  including explicit consent, lost committed reply, refresh and existing workspace
  preparation. PASS, exit 0, unchanged inputs. The reviewed wheel changes only
  compiled frontend assets/index and RECORD from the initial tested wheel.
- `evidence/local-check-ui/consent-False.png`: inspected consent form; visible
  explanation, unchecked permission and disabled action before approval.
- `evidence/local-check-real-codex.json`: actual installed HTTP endpoint ran the
  real Codex version command, returned 200/version 0.159.3, and stored one local
  observation with zero sessions, bindings and realizations. This was the initial
  wheel, whose backend bytes are identical to the reviewed wheel. No provider
  conversation or compatibility qualification is implied.

Windows: Python 3.13.1. WSL Linux: Python 3.12.13. Synthetic versions in automated
backend/UI tests do not replace the separately recorded real Codex observation.
The shared Starlette/httpx deprecation warning remains. Initial source evidence
is retained in `evidence/local-check-source.xml` and is not final installed proof.

Initial Nexus wheel SHA-256:
`3a91d4c04ac657f2acb813f611707f5222c710c8c46d30f0424470abe8e1c246`.
Initial sdist:
`26795b49b8d9476ff3c8286ad7a3c7809319dd610c298e4778084793f7591b75`.
Reviewed Nexus wheel:
`a88806df6e7110d22ef8d841ac78bc68eabfd467daa4d533d95c3b7b46d3c988`.
Reviewed sdist:
`c413124c4d4d774de1737a8b447649b212bf8c499e65c1206d145361be092868`.
Dependencies remain Core .56 wheel `7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6`
and Connector issue-2 wheel `93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

## Reproduction and remaining acceptance

Build with `python tools/build_validation_artifacts.py --output <dist>` and install
the resulting wheel in the isolated test environment with the manifest's Core and
Connector wheels. Run `tools/ci_installed.py test --wheel <wheel> --output <fresh-dir>
--tests tests/execution_r4/test_local_installation_check.py` using that environment's
Python. Add `test_local_installation_check_dashboard.py` and
`test_embedded_preparation_dashboard.py` from the same test directory with
`OKTO_NEXUS_UI_CAMPAIGN=1` and the installed browser prerequisites for UI acceptance.
Campaign JSON records all monitored input hashes and exact invoked tests.

Operator instructions are in `docs/harness-integrations/r4-operations.md`.
Runtime operation controls, remaining onboarding and provider/platform acceptance,
final three-repository freeze and G0–G3 remain open. CI is deferred; independent
hosts require the user's manual intervention. Native macOS Intel development now
has a user-operated test host, with an initial feasibility diagnostic in Core's
`plans/MACOS_INTEL_IMPLEMENTATION.md`; support remains unqualified.
