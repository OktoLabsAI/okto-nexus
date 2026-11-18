# Browser-only outer gate

This supersedes only the earlier absence of an outer runner in `plan.md`.
All earlier prepared inputs remain unchanged. No runtime has been executed.

`run.py --gate <new-approved-json>` validates the new bound manifest, R9 READY,
wheel, all1031 installed files,1829 source pins, Node/Chrome executable hashes,
and all192 qualified CLI/Playwright tool files BEFORE allocation. It requires
CLI0.1.24, own config and an explicitly approved browser-only gate. It imports
only the pinned S1/R9 `Commands` manager and browser environment/capture helper;
it does not call their main function or any Nexus fixture lifecycle.

After the gate, the qualified allocation helper copies prepared files only.
The outer starts direct Node+CLI with the existing path-only Windows allowlist,
empty executable PATH, own cwd/global-config/daemon directories, explicit own
profile and pinned Chrome config. There is no npx/npm/install/update path.
The own main Chrome is captured with exact profile, executable hash and birth.
The separate static probe runs under R9 Python `-I -B`, own homes and empty PATH.
No Nexus module/application, setup Test, provider or native runtime is started.

The native UI/geometry script is unchanged. A first error or NOT_RUN result
stops the flow; no fallback or application stage exists. All commands write
unique artifacts (`launch-browser`, `native-guard`, `cleanup-browser`) so phase
names cannot collide. Normal CLI close and probe stop happen first. The action
window reserves30s within the180s process deadline for cleanup. Any required
birth/executable-fenced containment is retained as DIAGNOSTIC_FAIL even if it
leaves zero resources; it is never reported as normal cleanup. Final immutable
audits occur after processes are stopped.

The curator independently rechecks known births, own-profile processes and the
probe listener before publishing explicit logs, native UI/probe screenshots and
metrics. It never copies Chrome profile/preferences/OS config. It verifies no
Nexus-ready/origins artifacts exist. The published result is native-browser-only,
with I05 application NOT_RUN regardless of the native zoom result.

Proposed future commands, not authorization:

```
rtk proxy <host-python> -B run.py --gate <new-approved-browser-only-gate.json>
rtk proxy <host-python> -B curate.py --root <own-root-from-output>
```

`GATE.template.json` remains false. Root must supply a new true gate bound to the
exact `prepared-bound.json` hash. The one invocation may launch only its own
Chrome, direct toolchain and static HTTP probe. A Nexus/UI phase needs separate
review and authorization after this proof. There is no performance, reader,
human or200%-equivalence claim from syntax validation.
