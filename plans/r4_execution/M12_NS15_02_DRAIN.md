# Legacy-owner drain and migration admission

`tests/execution_r4/test_ns15.py::test_ns15_02` starts two legacy sessions through
the real TCP application, then requests the public R4 shutdown endpoint. The
actual Server coordinator, dispatcher, supervisor, journal and SQLite projection
perform teardown. Technical peers report one observed stop and one uncertain
active turn; they are not provider qualification.

The test checks one end command per peer, teardown through the owning connector,
closed admission, released dispatcher, retained public history and refused new
legacy opening. It then takes an offline backup, runs catalog migration and
checks the exact adoption guard: observed stop is eligible for review; unknown
remains refused. No Core session is created and neither historical session row
is rewritten. Both physical stops are observed; the second turn result remains
uncertain. The existing combined backup/restore procedure then restores into a
new home, refuses missing quiescence acknowledgement and starts the supported
application with execution disabled. Authorized history is readable, unauthorized
history and new opening are refused, and the restored unknown still blocks
adoption. The supported CLI shows HTTP help and refuses `stdio`.

This exposed a product defect: the actual owner projects `ENDED`, whereas the
adoption guard compared only lowercase `ended`. The guard now compares the
terminal status case-insensitively and requires the persisted end timestamp.
It also refuses contradictory active/unknown/detached lifecycle states even if
the row carries a terminal status. Legacy `legacy_unlinked` terminal records
remain readable and adoptable after review.

Restore also exposed a second defect: disabling execution disabled authorized
historical reads. `read` and `events` now bypass provider/feature availability,
while the existing authentication, grant, scope and audit checks remain in force.
No mutation is enabled by this exception.

The initial preparations used the legacy x-api-key header on R4 and expected a
lowercase status; those failures are retained separately from the actual product
reproduction (confirmed stop refused by the migration guard). Three negative
cases cover terminal status with unresolved lifecycle.

See `test_runs_20261001_ns15_02.json` for artifact hashes and results. This covers
TR4-15-02 through the supported offline restore path and current HTTP-only binary;
it does not qualify arbitrary older binaries. NS15.04 still requires its complete
configuration/marker and post-R4-effect restore criteria. The tested snapshot has
legacy runtime state, not active Core runtime stores. Full M12 and release gates
remain open.
