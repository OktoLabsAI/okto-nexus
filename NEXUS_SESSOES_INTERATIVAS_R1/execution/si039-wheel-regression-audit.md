# SI-039 regression audit against installed wheels

The default repository pytest configuration places `src` on the import
path. Some earlier regression runs in a wheel environment therefore used
the Nexus checkout. The rerun cleared the pytest checkout path with
`-o pythonpath=` and asserted that Nexus, Connector and Core were imported
from the fresh environment's `site-packages`. Both browser scenario
fixtures ran outside the checkout. A separate collection check from their
original directories confirmed that they import the wheels. The installed
bundle and native observations remain in their respective reports.
[Wheel digests and installed browser journey](si039-installed-journey.md)

All 170 distinct pytest cases in the rerun passed. Counts are shared where
the same case supports more than one scenario. The new JUnit digests are
the wheel-regression proof for the linked milestones.
[Checked modules and JUnit digests](si039-wheel-regression-audit.json)

| Claimed regression coverage | Cases passed from wheels |
| --- | ---: |
| Home rollback and disabled admission recovery | 29 |
| Historical receipt migration and queue storage | 20 |
| Installed browser and terminal package regression | 61 |
| Exact Codex build grants | 16 |
| Terminal guide commands | 69 |
| Dispatch and saved resume | 48 |

The repository CI runner already isolates installed-package imports using
a separate pytest configuration. This increment updates the local evidence
and the reproduction command for the new rollback regression. The full
provider qualification gates remain open.
[Installed regression runner](../../tools/ci_installed.py)
