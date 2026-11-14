The retained bytes are part of the frozen qualification evidence. `git diff
--check` reports twenty trailing-space occurrences in the historical failed
`preparation/evidence/affected-001/results.xml` and one extra blank EOF line each
in `preparation/draft/controller/api_worker.py` and
`preparation/tests/controller/canonical_fixture.py`.

These three evidence copies are preserved byte-for-byte to match their qualified
hashes. The exception applies only to those whitespace categories in those
files. Other staged files pass the normal whitespace check; no product source
is exempted.
