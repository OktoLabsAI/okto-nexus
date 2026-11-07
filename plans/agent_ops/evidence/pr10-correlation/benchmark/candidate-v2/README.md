# Installed OBS12 measurement campaign V4 against candidate-v2

The measurement driver and preflight script are byte-identical to V3. Only the
candidate proof/interpreter CLI references change. The candidate-v2 wheel is
fc9bb8f075ac0167eee9c21d96592b12d46c218df77a0f2114f44b1fc20b1355.
V3's 86/90 samples and four budget refusals remain immutable in its original
directory; parent-v3-manifest.json is a byte-preserved provenance copy. No V4
measurement may run until the coordinator's explicit GO after installed tests.

V3 corrects only the Core distribution lookup to `okto-nexus-connector-core`
(import `nexus_connector_core`). The failed V2 attempt stopped in preflight before
bootstrap, seed or measurement; its sanitized report and final manifest remain
in the original V3 folder unchanged. This was qualification infrastructure, not a product failure or
a performance sample. The approved workload is unchanged.

Coordinator-approved campaign: 2 fresh synthetic layouts (1 native session and
64 native sessions), each growing through 64 / 512 / 4096 OBS instances, 3 samples
per read at every scale. Four operations with three receipts each are persisted
through the production receipt producer for every native session. This is not a
qualification of 4096 distinct native sessions or real OS birth evidence.

V2 alternates global instance indices: 50% blocked and 50% working. Every instance
remains explicitly correlated. Expected batch cardinality is N; attention blocked
is N/2 (all-kind attention may also include other canonical facts); summary is N
with exactly N/2 blocked, N/2 working, zero idle/unknown and all N current. No
external completion events are seeded.

This is not an identical workload comparison with the earlier OBS11 baseline,
which included external completions. This campaign measures correlation and
12 canonical receipts per session. The prior 100%-blocked V1 remains prepared,
unexecuted and unqualified in its original directory. Its manifest is retained
byte-for-byte as parent-v1-manifest.json.

The first prepared V2 and intermediate isolated-profile script/README/manifests
remain byte-for-byte in the original V2 directory's historical subdirectories.
Those intermediate versions were never executed.

Reads: private batch for all authorized fixture IDs, public service list200,
external-blocked attention page50, all-kind attention page50, external summary.
All keep the existing 5-second budget. Results preserve every sample, cold/less
warm first samples, error codes, SQL classes/counts and canonical-table equality.
The driver does not claim a general latency SLO. It makes no HTTP requests; the
separate HTTP test records the cold agents/api_key_hash lookup (6 vs warm5 for
attention) rather than confusing that authentication cost with per-item SQL.

Product imports and all installed package bytes are verified against the supplied
package proof before and after the run. No checkout/test imports are used. Core
codec/receipt ingestion are permitted; runtime composition, journal opening,
process launch, harness discovery and artifact hydration are guarded to fail.
Every loaded okto_nexus and nexus_connector_core module/package path must belong
to the qualified venv. Core distribution metadata must resolve there and report
exactly version 0.0.14; the pinned Core wheel hash is checked as well.

Errors retain only class/code and bounded traceback filename/line/function fields.
They never retain exception text, locals, SQL or environment values. Preflight
failures also receive a separate sanitized JSON report, without overwriting a
previous report.

Before the first product import and before each layout's bootstrap, the driver
removes inherited application/provider environment variables by name, without
reading, storing, restoring or logging their values. USERPROFILE, APPDATA and
LOCALAPPDATA point inside that layout's disposable home. HOME and CODEX_HOME are
untouched and are never used to derive paths. Explicit --home and isolated Python
mode remain in force. No profile is created while merely preparing this script.

The fixture homes contain only synthetic data, but remain private: do not collect
DB, WAL, SHM, publisher credentials, raw native proof, frame bodies, SQL text or
hashes of these database files. Canonical row fingerprints stay in memory; only
equality booleans and table counts enter the shareable JSON.

Receipt-time limitation: the installed batch treats any noncanonical/invalid
receipt timestamp in a selected session's history as unknown, preventing an old
valid receipt from becoming an apparently current fallback. Valid current
production receipts use canonical UTC timestamps with millisecond precision.

Prepared invocation (DO NOT execute until coordinator sends GO):

```powershell
rtk proxy C:/Users/jpamb/AppData/Local/Temp/pr10b-correlation-installed-7g83osyy/candidate-v2/venv/Scripts/python.exe -I -B C:/Users/jpamb/AppData/Local/Temp/pr10b-installed-benchmark-v4-s7u3zpr_/benchmark_installed.py --go --proof C:/Users/jpamb/AppData/Local/Temp/pr10b-correlation-installed-7g83osyy/candidate-v2/package-proof.json --dependency-path C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages
```

Each run requires absent fixture homes and a new output filename. Never delete
failed fixtures implicitly or overwrite a report. A replacement campaign should
use a newly prepared directory. `--session-count` is bounded/configurable for a
separately approved experiment; the approved run uses the default64 only.

Before the campaign, preflight.py uses the same qualified Python, --proof and
--dependency-path arguments. It validates imports/Core0.0.14, guarded bootstrap,
configuration, migration and empty public service reads in a separate disposable
home. preflight.json contains no timing samples. Only a PASS authorizes proceeding
under the coordinator's existing GO. Campaign outcomes are recorded separately.
