# Reading the retained package cuts

Each package directory retains its original preparation README and manifests.
Those preparation instructions describe their state when written. Subsequent
`READY.json`, `qualification.json` and `live-qualification.json` record execution.
Do not replay preparation commands against an existing allocation.

R3 executed the installed selection: 746 passed, eight literal platform/TTY
skips. Launcher and collection antecedents remain separately recorded.

R4 completed build, installation, smoke, Twine, byte audits and live HTTP/MCP.
It did not execute pytest. Its reuse of R3 backend test evidence is restricted
to the exact 1,024 module-payload files in `runtime-equivalence-vs-r3.json`.
R4 static assets changed and need separate UI evidence.

R5 changes backend progress classification and therefore requires fresh Home
installed tests. Its new allocation and wheel cannot inherit R3/R4 Home
qualification merely because all packages use development version 0.3.7.
