# Prepared about:blank diagnostic — not executed

This is not another S1 run. It allocates no Server, workspace, identity, grant,
native peer or provider. It imports only the existing host `Commands` supervisor
and sanitized-environment helper, asserts that no Nexus/Core/Connector product
module is loaded, and opens an own browser profile on about:blank.

Use explicit installed Node and the CLI JS already present in the previous own
Temp cache. Pin Node, Chrome, config, controller bytes and all192 files in the
three CLI packages before and after. No npx/npm command or package/browser
installation is used. `NO_UPDATE_NOTIFIER=1` makes the pinned CLI's update-check
function return before its npm subprocess or installed-skill checks. Own
HOME/USERPROFILE/APPDATA/LOCALAPPDATA/TMP and empty PATH remain; no personal
environment/profile or CDP/extension is restored.

The supervisor is reused, not replaced. A new Root gate must contain:

`approved:true`, `approved_by:"root"`, `kind:"BROWSER_ONLY_ABOUT_BLANK"`,
`owner_seconds:90`, `allow_own_containment:true`, a unique
`cut_id:"hst-browser-only-..."` and this directory's exact `manifest_sha256`.
An exclusive attempt marker is created after all validation, before its single
Temp allocation. No gate is supplied in this preparation.

One invocation performs open(timeout50s), a literal URL/title/context-pages
read(timeout10s), then normal close(timeout10s). The owner window is90s; a
final5s normal-settlement wait and at most5s exact birth/exe containment preserve
cleanup if necessary. No retries. Any failure, forced stop, survivor, listener,
guard drift or product import keeps FAIL/inconclusive. Timings are deadlines
for diagnosis, not latency/SLO claims.

`DEBUG=pw:browser*,pw:api` goes only to own private CLI/daemon logs. Phase markers
report START/COMPLETE and the unique Temp root, not debug contents. Curation
keeps raw logs/hashes separate; no raw logs are copied to the repository.

Proposed commands, **NOT RUN**:

```powershell
rtk proxy python -B .../browser-only/run.py --gate NEW_ROOT_GATE.json
rtk proxy python -B .../browser-only/curate.py --root OWN_DIAGNOSTIC_TEMP
```

Only a confirmed diagnostic result can justify a subsequent S1 instrumentation
change. This does not qualify Home, security behavior or performance, and does
not reinterpret either preserved failed S1 antecedent.
