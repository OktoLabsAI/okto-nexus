# Persistent ASGI counterpart — preparation only

No benchmark, process, Server, native peer or provider was started by this preparation. A new explicit Root performance window and frozen candidate READY are required before running `persistent-launch.py`. The original twelve measurements and all their FAIL thresholds remain untouched.

`persistent-prepare.py` reads the original measurement and current effect guard as text/AST and generates `persistent-worker.py`. It retains the original ownership/DB/schema gates, controlled clock, routes, pagination parameters, productive-table snapshots, statement tracing, 3 warmups, 20 samples, nearest-rank p95, 500 ms read target and 2 s HTTP proxy target. Installed `-I -B`, all three package origin checks and start/end wheel/payload comparison are still performed by the original main. No lifespan, background startup, TCP HTTP listener or provider is used. Popen remains a subclass to preserve runtime typing; connect/connect_ex/sendto remain blocked except the original Windows socketpair in a current-thread depth fence.

The experimental difference is one `asyncio.run` containing one `httpx.AsyncClient(ASGITransport(app))` for every first request, warmup, traced read and sample. This avoids creating a TestClient portal/event loop for each synchronous request. It still includes ASGI middleware, thread-pool handoff where production handlers use it, serialization and response decoding. It is a transport/lifecycle comparison, not evidence that the original overhead caused its timings, and cannot replace browser first-useful DOM timing or production/network latency.

The prepared launcher copies the **unmeasured original seed home** to a new named own Temp dataset and proves the copied DB SHA/schema equal the original manifest. It supports the mixed 1/10/100 datasets and separate 100-open complement. Original clones, seeds, manifests and reports are never reset/reused/mutated. Each invocation selects one size/variant. New outputs and launch reports refuse overwrite. The child has closed PIPE stdin, own environment homes/TMP and no inherited provider settings; launcher containment is limited to its own child. A 240-second outer deadline preserves the original 180-second measurement budget and records timeout as a timeout, never PASS.

Example shape, **not yet executed**:

```text
rtk proxy python -B persistent-launch.py --window PERF_WINDOW_OPEN --ready <future-frozen-READY.json> --dataset <original-dataset.json> --connections 100 --variant candidate-v2 --label <new-cut>
```

The launcher must be invoked by the host orchestration Python; it starts the selected installed READY Python with `-I -B`. New candidate schema incompatibility, changed fixture/helper pins, source seed drift, unknown/partial HTTP data, incomplete samples, productive effects or payload/origin drift fail closed. No claim of performance improvement exists until execution under a newly released exclusive CPU window.
