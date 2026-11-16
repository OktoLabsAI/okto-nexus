# Actual HTTP overview endpoint — HOME031 / §9

One dedicated finite runner measured GET /api/v1/home/overview over real
loopback TCP in four owned Uvicorn processes. Each case used the existing seed
function, one discarded real HTTP warmup and20 warm keep-alive requests. No
browser, SSE, app lifespan or discovery competed with these requests. Canonical
loopback authorization and the real clock remained unchanged.

| Workers / handoffs / events | HTTP p50 ms | HTTP p95 ms | Local500ms p95 target |
| --- | ---: | ---: | --- |
|1 /10 /100 |244.48 |281.28 |Met in this sample |
|10 /10 /100 |217.50 |227.64 |Met in this sample |
|100 /10 /100 |180.60 |289.28 |Met in this sample |
|100 /1000 /100000 |401.47 |450.32 |Met in this sample |

The timer covers the actual HTTP request/full body; subsequent client JSON
parsing and the private control-pipe statistics are outside it. Every one of
the84 requests returned200 and valid canonical body counts/scope/event cursor,
with no-store. Observation covered the app shared factory, including any auth
use: exactly one declared read UoW,46 traced SQL statements, zero row changes
and zero denied mutation attempts per request. Body max11477 bytes, no content
compression in this run. The slight read-only fixture middleware adds overhead
and does not replace an endpoint or auth path.

All four servers acknowledged normal shutdown and physically exited with code0
through retained process handles. No force/restart was used. The new allocated
Temp root was removed only after all child joins. No provider, native harness,
personal account or system service was used.

Runtime sources match frozen head3d95aad8 before/after; all699 Nexus source
payloads also compare byte-for-byte against the qualified c1c45e2a wheel. The
script, selection marker and all20 per-case request samples are retained here.
The selection marker prevents accidentally rerunning/replacing this experiment.

These are local endpoint samples, not production SLO approval. The earlier
service-only experiment, including its large-case673.91ms p95 miss, remains in
pr08-performance-final. Its preparation/process/cache/timing paths differ from
this dedicated HTTP run. They are separate experiments; subtracting their
numbers or claiming HTTP is intrinsically faster would be unsupported. Browser
first-use/render timing and live native work are distinct qualifications.
