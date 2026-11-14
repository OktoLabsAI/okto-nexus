# DX-T34: missing provider login, native execution

DX-T34 is verified: the installed CLI reported `PROVIDER_AUTH_REQUIRED` with a concrete login command and the approved temporary provider home. The same daemon remained ready, then stopped normally with physical exit confirmed. The post-exit journal projection records `runtime.open` as FAILED and zero turn actions or turn receipts. This does not qualify SVC-T15 or M1.

The [actual result](execution/result.json) and [review](review.json) bind the corrected [driver](sources/resume_case.py). Root executed it with the isolated installed Python and explicit `-X utf8`; no script arguments were used. The curator copied evidence only and performed no native or service execution.

Both failed attempts are retained. The [original run](history/original-run/result.json) could not decode plan JSON produced with Windows CP1252; `-I` ignored the proposed environment encoding setting. The service stopped normally. The [first continuation](history/first-resume/result.json) then failed on an absent PID key before starting a service; its [source](history/first-resume/driver-before-absence-fix.py) is retained. The final continuation checked canonical absence and reused the existing reviewed plan for its first apply. It performed one explicitly selected normal restart, beyond the original proposal's one-start scope; it did not repeat plan, native preflight, or apply.

The original preparation metadata remains historical and unchanged. Its 20-case initial and final runs are not counted as 40 distinct tests. Numeric-bound compilation and root-reported UTF-8/absence checks are distinguished in [root observations](root-observations.json). Raw private output, database files, provider config/auth files, and installed packages are excluded. The public journal summary preserves `possible_effect=true` and `retry_safe=false`; zero model turns does not change those fields.

The ledger and commits are left to the root agent. The retained sources are evidence, not an instruction to rerun this completed campaign.
