# M1 v14: HTTP latency diagnosis

This package preserves bounded, sanitized observations of the owned Nexus PID 5132, generation `c9f085a3b8f3f61558fb5ad9cc302ee2`. It identifies plausible contention paths; it does not establish a definitive cause or promote any acceptance criterion. Curation made no live requests, service changes, provider calls or new test runs.

| Evidence | Observation and limit |
| --- | --- |
| [Initial diagnosis](unresponsive.json) | `connections/me` timed out after 10.485 s with a 10 s timeout. A read-only SQLite snapshot succeeded; that does not exclude writer contention. Two approximate stack samples exposed an IOCP poll and synchronous heartbeat work, not a time attribution. |
| [Superseded CPU calculation](cpu-initial-superseded.json) | The initial per-process percentages used the wrong elapsed denominator and are explicitly invalid. Three separate main-thread samples at 17:33:41–44 UTC showed `asyncio.windows_events._poll`. Only normalized top frames are retained, without raw headers or locals. |
| [Corrected CPU measurement](cpu-corrected.json) | At 17:38:22 UTC the host was at 97.9%. Nexus used 0.4375 CPU seconds over its 8.299 s sampling window: 5.27% of one logical CPU, or 0.33% of total 16-CPU capacity. Per-process windows differ slightly; generic Python process ownership is not inferred. |
| [Three later GETs](three-get.json) | At 17:39:15–16 UTC the protocol path returned 404, `connections/me` returned 200 in 50 ms and `/service` returned 200 in 11 ms. The owned listener PID was unchanged, and `/service` confirmed the same generation and readiness. These observations show recovery, not its cause. |
| [Later adoption projection](adoption-result-projection.json) | The public result records `CONFIGURED_PREDECESSOR_ADOPTED`, GET-only observation, no setup replay and zero new model admissions/tokens. Its source hash is recorded in the manifest. This does not prove useful work or broader acceptance. |

The source heartbeat fix was committed separately as `9379d207`; [its retained evidence](../r3-http-heartbeat-isolation.md) records 30 passing tests. It moves filesystem heartbeat work off the HTTP event loop while preserving cleanup ownership. The active M1 installation was unchanged, so the later successful HTTP responses cannot be attributed to that source fix.

The [GET writer qualification](get-writer/qualification.json) and [three focused tests](get-writer/test_connections_me_writer_contract.py) characterize the actual FastAPI route against an isolated SQLite fixture. The route reaches `BEGIN IMMEDIATE` and waits while an external writer holds that transaction; a read-only snapshot remains available, and releasing the writer lets GET finish. This establishes a possible contention mechanism, not that it caused the live timeout.

Changing the route to `persist=False` would change its revision contract: without a baseline, successive configurations keep revision 1; with baseline A, read-only B and C both project revision 2, whereas existing GET persists B=2 then C=3. Boot and key issuance do not supply those missing revision baselines. No product patch was made to this route.

The initial characterization result (2 passed, 1 failed) is retained alongside the final result (3 passed). The failure came from attaching SQL tracing after the first GET, missing the cached per-thread connection; attaching it before that request corrected only the fixture. The retained final test file is the corrected fixture, not an exact snapshot of the initial failing run. The runner imported Nexus source explicitly through `sys.path`; it was not an installed-Nexus qualification. The exact command is in `qualification.json` and was run from the original Temp fixture directory.

`manifest.json` records source and retained hashes. Three diagnostics and four fixture/qualification files are byte-identical copies. The superseded CPU and adoption artifacts are explicitly narrowed projections. No raw py-spy process header, command line, environment values, credentials, transcript, provider output or live database is retained. Ledger and acceptance statuses are unchanged.
