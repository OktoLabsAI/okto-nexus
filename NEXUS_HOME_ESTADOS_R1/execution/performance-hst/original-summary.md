# Original performance cuts

FAIL: the 500 ms p95 target is missed by all 100-connection cuts. These results remain antecedents of the revision/SQL optimizations.

| Workload | Connections | Variant | Overview p95 ms | Activity page p95 ms |
|---|---:|---|---:|---:|
| mixed | 1 | baseline-v1 | 218.542 | 228.256 |
| mixed | 1 | candidate-v1 | 213.742 | 213.920 |
| mixed | 1 | candidate-v2 | 213.831 | 191.979 |
| mixed | 10 | baseline-v1 | 320.099 | 269.273 |
| mixed | 10 | candidate-v1 | 323.888 | 316.722 |
| mixed | 10 | candidate-v2 | 352.937 | 299.200 |
| mixed | 100 | baseline-v1 | 982.406 | 928.311 |
| mixed | 100 | candidate-v1 | 973.592 | 1032.852 |
| mixed | 100 | candidate-v2 | 1147.227 | 1125.285 |
| open | 100 | baseline-v1 | 953.670 | 898.473 |
| open | 100 | candidate-v1 | 854.293 | 1076.893 |
| open | 100 | candidate-v2 | 946.139 | 1170.809 |

HTTP/ASGI only: first useful DOM target 2s remains NOT_RUN.
TestClient creates a fresh AnyIO portal per GET; original timings remain failed, not corrected retroactively.
Mixed 100-case has 925 terminal and 75 open activities; separate OPEN dataset has 1000 open activities and 100000 history events.
Synthetic SQL performance facts do not qualify real runtime, authority, grants or native causal progress.
No latency claim applies to later source optimizations or a future candidate package.
Diagnostic cProfile costs overlap and are not additional p95 measurements.

All twelve workers exited with HTTP 200/ready, zero productive-table drift and unchanged installed wheel payloads. Per-process exit evidence remains in the corresponding `*-launch.json` files. Raw samples and exact report hashes are retained in `original-timings/` and `original-summary.json`. Infrastructure failures are preserved as build-attempt1/2 and profile-antecedent; they are not latency results.
