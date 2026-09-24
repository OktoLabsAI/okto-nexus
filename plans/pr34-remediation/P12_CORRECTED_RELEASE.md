# Corrected source qualification and release preparation

Implementation commit: ff905c433e1a92ae35993b2189919f75ad07dd51, pushed to
feature/v0.2.0. No merge. Source corrections and main integration evidence are in
P12_RECEIPT_GROUPING_REGRESSION.md. The final aggregate gate is still pending.

Corrected Windows full regression49697 runs the frozen detached39c5e6c plus
five-path candidate. Comparison against543 tracked files in the integrated Git
commit found12 exact byte matches and531 UTF-8 text differences consisting only
of CRLF versus LF; no other differences or candidate mutations. An initial strict
all-byte comparison failed on those line endings and was not mislabeled PASS.
[evidence/p12-candidate-commit-equivalence.json](evidence/p12-candidate-commit-equivalence.json)
retains the full distinction, base/diff hash and scope. Binary files require exact
matches. This proves explicit normalized-source equivalence, not identical raw
bytes or a fabricated committed SHA for the original Windows launch.

Corrected Linux full regression19457 now runs a clean detachedff905c4 checkout at
/var/tmp/okto-pr34-final-source-jzx6swb0/source, with import origin verified inside
that checkout. Private command/status record:
.git/pr34-evidence/full-ff905c4-linux-nativefs-launch.json. Fixtures are new under
/tmp; result XML/log remain on D. Native/browser campaigns are explicitly disabled
in both full suites, with their separate qualification retained. Both full runs
are still pending and must be observed terminal before final acceptance.

## Package preparation

A fresh git archive offf905c4 excludes all pre-existing local generated asset
modifications. uv lock --check, npm ci, TypeScript/Vite build to a private output
directory, uv build and actual Twine wheel/sdist checks completed successfully.
The first Twine launcher could not import the installed user-site package because
its USERPROFILE was deliberately temporary; restoring only PYTHONUSERBASE for the
existing validator fixed environment resolution. That exit1 is retained as a
preparation failure, not a rejected artifact or successful check.

The wheel contains64 additive SQL migrations, runtime_external_work.py, the exact
corrected inbox.py and byte-matched freshly built dashboard assets. Vite's existing
large-chunk warning is retained. No user assets were overwritten, and the global
installed version has not yet been changed. Final manifest and exact artifact
hashes: [evidence/p12-release-ff905c4.json](evidence/p12-release-ff905c4.json).

Required remaining actions: terminal full-suite manifests and requirement joins,
final task/phase/readiness reconciliation, local installation and installed isolated
validation. Native Codex/Claude at this exact implementation commit passed; see
P12_NATIVE_FRAMES.md. Pi and dedicated attach retain authorized NOT_RUN status.
Plan-only operational measurement now covers previously absent timing boundaries;
see P12_OPERATIONAL_METRICS.md. These instrumented timings are not replacement
comparative benchmarks.
