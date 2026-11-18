# Persistent ASGI comparison

**FAIL:** all eight 100-connection cuts exceed 500 ms p95. All six 1/10-connection cuts meet 500 ms. First useful DOM remains NOT_RUN.

| Case | Overview p95 ms | Activity p95 ms |
|---|---:|---:|
| mixed-1-baseline-v1 | 145.302 | 152.499 |
| mixed-1-candidate-v1 | 134.084 | 133.404 |
| mixed-1-candidate-v2 | 156.387 | 147.261 |
| mixed-10-baseline-v1 | 219.675 | 223.804 |
| mixed-10-candidate-v1 | 231.092 | 211.708 |
| mixed-10-candidate-v2 | 215.880 | 202.095 |
| mixed-100-baseline-v1 | 866.955 | 879.162 |
| mixed-100-candidate-v1 | 990.603 | 1151.716 |
| mixed-100-candidate-v2 | 836.589 | 804.979 |
| mixed-100-r1-v2 | 1035.178 | 997.927 |
| open-100-baseline-v1 | 719.566 | 611.727 |
| open-100-candidate-v1 | 576.132 | 580.100 |
| open-100-candidate-v2 | 640.500 | 652.926 |
| open-100-r1-v2 | 748.514 | 718.274 |

Persistent httpx ASGI transport, one loop per worker, no lifespan/background service/TCP/browser.
Synthetic SQL read facts do not prove runtime readiness, real authority or native causal resumption.
Original 12 fresh-TestClient measurements remain immutable FAIL antecedents; no corrected/replaced timing claim.
R2v2 is lower than R1v2 in both measured 100-case workloads, but still misses 500 ms; v1 performance is mixed.
A single paired series per package/workload does not establish confidence intervals or universal improvement.
No real provider, personal credential, external network request or productive write was executed.

All 14 workers exited0 physically. Each report contains 20 raw samples per series, byte counts, query counts, package origins/hashes and start/end immutability checks. New byte-identical clones came from the unmeasured original seeds. No infrastructure retry occurred. The launcher preparation fixed a duplicate `cwd.mkdir` before any worker execution; that change is isolated from product code.
