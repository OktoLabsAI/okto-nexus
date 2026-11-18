# S1 R9 comment-only counterpart — not executed

The original a4709e… base and cut0879f0… remain unchanged. Chrome open,
actual own-profile proof, state load and normal close succeeded there; its first
failure was a host template guard before Home because the placeholder literal
also appeared in a JavaScript comment. It did not execute the security phases.

This wrapper changes **only that comment**, preserving the const cfg placeholder,
the original occurrence-count guard and every scenario assertion. The new JS
bytes equal original bytes with one exact comment replacement; no newline or
other formatting rewrite. Both effective S1 templates must have exactly one
placeholder before any runtime. Node --check is performed statically.

The unchanged base driver reads its unchanged template path. A temporary host
Path.read_text hook substitutes only that exact path and only the approved
comment replacement; all other reads are returned untouched. The installed
application is a separate process and receives no hook, fake response, DTO or
authority. The hook is restored in finally. Pre/post variant proof binds the
effective template hash and the base manifest; normal full source/payload/
browser/30-table/revocation/cleanup guards are unchanged.

A new Root gate/cut ID is required. Keep manifest_sha256 = base
`a4709ef7f680c8fb61e9ac53ba005dfdd5885c0eb12e44cce69ad20ba2a6a43d` and all
approved S1/R9/environment fields. Add `comment_variant_manifest_sha256` for this
directory and `effective_template_sha256` for its s1-passive.js. Use a fresh
hst-security-r9-s1-... cut ID. Base driver retains the exclusive attempt marker.

Proposed commands, **NOT RUN**:

```powershell
rtk proxy python -B .../comment-only-v2/run.py --gate NEW_ROOT_GATE.json
rtk proxy python -B .../comment-only-v2/curate.py --root OWN_TEMP_FROM_RUN
```

No new Chrome strategy, scenario, provider, product/prefix change, S2 or SLO
campaign. Curation retains the failed antecedent and all layer/cleanup limits.
