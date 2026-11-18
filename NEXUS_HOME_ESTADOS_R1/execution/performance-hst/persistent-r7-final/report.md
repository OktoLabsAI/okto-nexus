# Final R7 persistent-ASGI measurements

Candidate HTTP/read targets: **FAIL**. Candidate counts: {'measured': 8, 'read_target_pass': 5, 'read_target_fail': 3, 'first_http_proxy_pass': 8, 'first_http_proxy_fail': 0, 'not_run': 0}. Baseline counts: {'measured': 2, 'read_target_pass': 0, 'read_target_fail': 2, 'first_http_proxy_pass': 2, 'first_http_proxy_fail': 0, 'not_run': 0}.

| Case | Overview p50/p95 ms | Activity p50/p95 ms | Queries overview/activity | Bytes overview/activity |
|---|---:|---:|---:|---:|
| mixed-100-baseline-v1 | 620.258 / 679.093 | 706.229 / 965.972 | 52 / 52 | 252835 / 27965 |
| mixed-100-candidate-v1 | 898.003 / 1048.092 | 819.394 / 946.510 | 51 / 51 | 281050 / 31188 |
| mixed-100-candidate-v2 | 780.406 / 876.423 | 797.406 / 927.279 | 53 / 53 | 297313 / 31730 |
| open-100-baseline-v1 | 730.475 / 878.034 | 737.777 / 849.271 | 52 / 52 | 162252 / 20520 |
| open-100-candidate-v1 | 681.224 / 752.154 | 595.506 / 651.248 | 51 / 51 | 162307 / 20575 |
| open-100-candidate-v2 | 407.251 / 497.934 | 411.430 / 489.176 | 53 / 53 | 174986 / 21117 |
| mixed-1-candidate-v1 | 130.504 / 150.201 | 92.031 / 105.605 | 51 / 51 | 77257 / 32375 |
| mixed-1-candidate-v2 | 87.912 / 133.488 | 112.504 / 138.143 | 53 / 53 | 82523 / 32915 |
| mixed-10-candidate-v1 | 200.159 / 250.906 | 174.361 / 228.518 | 51 / 51 | 291015 / 31172 |
| mixed-10-candidate-v2 | 174.988 / 259.198 | 149.716 / 173.070 | 53 / 53 | 307214 / 31713 |

Paired differences against baseline in this same window (positive is slower):

- mixed candidate-v1: overview +54.34%; activity -2.01%.
- mixed candidate-v2: overview +29.06%; activity -4.01%.
- open candidate-v1: overview -14.34%; activity -23.32%.
- open candidate-v2: overview -43.29%; activity -42.40%.

Persistent httpx ASGI, one loop per worker; no TCP/browser/lifespan/background runtime.
First HTTP proxy is not first-useful DOM. No DOM execution or DOM gate approval in this cut.
Own SQL synthetic facts do not qualify providers/native authority/liveness/grants or application of decisions.
No threshold waiver, retry, source/schema modification, or statistical confidence claim.
Query counts do not qualify internal SQL row-scan complexity.
Mixed100 contains925terminal/75open; OPEN100 contains1000open/100000history. Separate workloads.
Baseline failures are reported separately and do not determine candidate status.

Raw reports retain20samples per series and exact origins/bytes/guards. All10workers and orchestrator exited0 physically. No app reader remains; only stdlib curation followed.
