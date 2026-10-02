# M13 — Immutable campaign input coverage

The installed campaign previously hashed backend/test/docs inputs but omitted
frontend source and the validation scripts themselves. An installed-package byte
check proves which bytes ran; it does not prove that omitted build inputs stayed
unchanged during a campaign. Final freeze still requires exact commits/artifacts.

`tools/ci_installed.py` now additionally includes all files under `frontend/src`
and `frontend/public`, frontend root JSON/TS/JS/MJS/HTML build inputs, the installed
runner, artifact builder and CI workflow. It continues to exclude generated
node_modules, dist, tsbuildinfo and evidence output. The existing before/after
comparison now rejects changes or removals in these additional inputs.

The directed check creates a minimal workspace and proves that edits to TSX,
CSS, SVG, lock/config/index files and both scripts/workflow change the fingerprint;
deletion is detected and generated outputs do not invalidate the campaign.

Verification on 2026-10-02:

- Source helper test: one passed.
- Installed Windows/Python 3.13.1: two passed, including packaged OpenAPI.
- Installed WSL Linux/Python 3.12.13: the same two passed.
- Both campaigns captured 77 frontend input files and ended with no changed inputs.

The application artifacts were not rebuilt for this test-runner change. Windows
used the latest UI development wheel
`62121869d6a19b374d61eab513b03d3bdc42973b6d6567e03620b621c869dcf0`;
Linux used the prior HTTP development wheel
`2edfbcfb5f1076b5587a3b4c8d1fd50aa8e6f105168a54d0a1f7d4302b7704f4`.
Both used the same pinned Connector/Core bytes. These checks qualify the expanded
campaign guard and schema serving, not cross-OS acceptance of one final artifact.

[Windows campaign](evidence/campaign-inputs-windows/campaign.json),
[Linux campaign](evidence/campaign-inputs-linux/campaign.json),
[source check](evidence/campaign-ui-inputs-source.xml).

The Connector renewal follow-up at `beead27` reproduced two delayed-loop
renewal-entry timeouts as LEASE_EXPIRED and corrected their synthetic clock
boundaries without changing product policy. Its full installed Windows suite
passed 716 tests with two skips. Linux passed 710 with six skips and two missing
test-dependency setup errors; the two clean-packaging cases passed after installing
the declared build dependency. Later observer/boundary checks also passed on both.
See the [Connector evidence and limitations](https://github.com/OktoLabsAI/okto-nexus-connector/blob/beead27/plans/implementation/CI_RENEWAL_ENTRY.md).

Hosted event-recovery timeout diagnosis, legacy-peer coverage reconciliation,
remaining UI/provider/independent-host acceptance, final clean installation and
exact release freeze remain open. M13 and G0-G3 are not closed by this increment.
