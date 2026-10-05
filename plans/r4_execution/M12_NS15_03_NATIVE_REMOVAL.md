# NS15.03 native implementation removal — October 1, 2026

The Server production source tree no longer contains the Pi, Codex, Claude stream
or Claude attach native connector modules. Their protocol implementations now
live exclusively in `tests/legacy_native_fixture`, outside setuptools' `src`
package discovery. Existing regression tests inject these fixtures explicitly.
The relocation changes imports only; it preserves the historical domain tests
without making the old native implementations available in the installed Server.

The isolated-process boundary check now requires each retired module to be
undiscoverable, in addition to verifying that Server composition never imports
it and that retired default factories refuse execution. The installed campaign
also verifies that neither the four modules nor the fixture package occurs in
the wheel, and checks installed package bytes against the three artifacts.

Canonical callers, approved fallback, binding migration, historical MCP/REST
callers and every test module whose imports changed are exercised against the
installed Server. Fixture passes verify historical regression behavior; they do
not qualify a current Core adapter or a real provider. The 81 skips (72 platform
cases and 9 opt-in live-provider cases) remain explicit in the XML evidence.

The lifecycle campaign initially exposed four missing-fixture imports in the
generated serve launcher. Its isolated environment now includes the test fixture
directory and resolves the same Server package used by the parent test, rather
than forcing the checkout source path. This also exposed a stale injection hook:
the fixture patched the old MCP bootstrap alias instead of the neutral bootstrap
used by serve. It now injects its explicit connector at that actual composition
point, preserving production's refusal of default legacy execution. Both failed
run logs/XML are retained; the final lifecycle run verifies the corrections.
Existing relay restart helpers
still launch the checkout source, whose nonstatic bytes match the installed wheel.

The broad fixture campaign retained one obsolete default-factory expectation in
the activation test. That test now explicitly injects its historical adapter;
the separate rollout campaign reruns the affected module. The manifest preserves
the original failure and requires a passing result for the same XML test identity.
Pass totals deduplicate test identities across both campaigns.

Shared helpers are intentionally still present at this checkpoint:
`compatibility.py` supplies historical endpoint capability metadata and still
contains version-probe helpers; `secret_redaction.py` imports bounded-buffer and
frame error types. Removing their unused native process/framing implementations
requires separating these live compatibility consumers. NS15.03 therefore
remains partial, with normative TR4-15-03 unexecuted. Canonical-attempt policy,
NS15.04 configuration/restore and final provider/platform/release gates remain
open. Domain planners, handoff and historical persistence are preserved.

Reproduction: `run_ns15_03_native_removal.py`; `--resume --campaign fixtures`
runs the relocated fixture campaign against the already built and verified
artifact. Results and artifact hashes are recorded in
`test_runs_20261001_ns15_03_native_removal.json` and the associated `evidence`
logs, XML and installed manifest.
