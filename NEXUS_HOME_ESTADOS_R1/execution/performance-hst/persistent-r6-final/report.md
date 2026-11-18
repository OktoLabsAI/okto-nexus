# Final R6 persistent-ASGI measurements

**FAIL:** all six 100-connection cuts exceed the original 500ms p95 target. Four 1/10-connection candidate checks meet it. No threshold was relaxed; no retry or new optimization occurred.

| Case | Overview p50/p95 ms | Activity p50/p95 ms | Queries overview/activity | Bytes overview/activity |
|---|---:|---:|---:|---:|
| mixed-100-baseline-v1 | 939.644 / 1004.191 | 890.501 / 996.947 | 52 / 52 | 252835 / 27965 |
| mixed-100-candidate-v1 | 886.477 / 951.019 | 868.470 / 961.969 | 51 / 51 | 281050 / 31188 |
| mixed-100-candidate-v2 | 962.426 / 1087.258 | 996.890 / 1193.307 | 53 / 53 | 297313 / 31730 |
| open-100-baseline-v1 | 703.506 / 797.944 | 644.960 / 771.214 | 52 / 52 | 162252 / 20520 |
| open-100-candidate-v1 | 607.838 / 831.650 | 578.118 / 651.081 | 51 / 51 | 162307 / 20575 |
| open-100-candidate-v2 | 677.913 / 826.732 | 643.056 / 735.652 | 53 / 53 | 174986 / 21117 |
| mixed-1-candidate-v1 | 138.096 / 157.884 | 138.695 / 149.707 | 51 / 51 | 77257 / 32375 |
| mixed-1-candidate-v2 | 142.708 / 160.238 | 130.413 / 150.644 | 53 / 53 | 82523 / 32915 |
| mixed-10-candidate-v1 | 205.367 / 246.656 | 176.973 / 221.563 | 51 / 51 | 291015 / 31172 |
| mixed-10-candidate-v2 | 210.185 / 245.274 | 177.486 / 217.106 | 53 / 53 | 307214 / 31713 |

Paired p95 differences against the baseline in this same window (positive is slower):

- mixed candidate-v1: overview -5.29%; activity -3.51%.
- mixed candidate-v2: overview +8.27%; activity +19.70%.
- open candidate-v1: overview +4.22%; activity -15.58%.
- open candidate-v2: overview +3.61%; activity -4.61%.

Persistent httpx ASGI transport, one loop per worker, no TCP/browser/lifespan/background runtime.
First HTTP proxy met 2s in all cuts; this is not first-useful DOM. Prepared HTTP/browser experiment is not executed.
Own SQL synthetic facts do not qualify provider, native liveness/authority, real grants or decision application.
All original 12 and persistent R2 cuts remain immutable; later source optimizations do not rewrite their results.
Query counts do not measure internal SQL row-scan complexity. No target waiver or confidence-interval claim.
Mixed100 has 925 terminal/75 open; OPEN100 has 1000 open/100000 history. They are separate workloads.
No product/source/schema edits or new optimization were made during this window.

Every report preserves 20 raw samples per series, exact package origins/bytes, schema/seed ownership checks and productive-table snapshots. All ten workers exited 0 physically and the orchestrator exited 0. The exclusive window is closed; only stdlib evidence curation followed.
