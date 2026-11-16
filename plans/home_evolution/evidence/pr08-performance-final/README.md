# Fresh HOME031 measurement — A08 source3d95aad8

One finite run of the existing measurement script used1/10/100 workers and a
100-worker dataset with1000 logical activities/100000 events. Each case has20
warm samples after a discarded first read with EXPLAIN. One read UoW and zero
writes were checked with the existing SQLite authorizer/trace. No server or
provider was started.

| Workers / activities / events | p50 ms | p95 ms | 500 ms target |
| --- | ---: | ---: | --- |
|1 /10 /100 |338.82 |421.12 |Meets local sample |
|10 /10 /100 |312.40 |325.23 |Meets local sample |
|100 /10 /100 |306.53 |327.14 |Meets local sample |
|100 /1000 /100000 |593.68 |673.91 |NOT MET |

All cases used46 traced SQL statements/read. Payload max11458 bytes. The large
work set paged in11 pages with1000 distinct IDs. The target remains500ms; this
measurement does not qualify a production latency SLO or approve rollout.

All45 EXPLAIN plans per case were available. The largest plan has576 nodes,
including materialized home_attention(_all) and correlated scans. Static plan
labels alone do not establish quadratic behavior. The20-sample data grew from
~307ms to~594ms median for100x activities in the100-worker cases; dataset event
volume also changes, so this is not an isolated complexity proof.

One additional large-dataset process-first GET was profiled with cProfile.
It took1143ms under instrumentation: overview1.037s, sqlite.execute1.045s
cumulative/0.541s internal; activity projection1000 calls/0.206s and handoff
eligibility1000 calls/0.172s. Cumulative numbers overlap. The profile is not a
warm latency sample. No optimization was made from these observations.

measurement.json preserves the original script output, including exact source
pins, environment and complete EXPLAIN metadata. qualification.json verifies
all measured backend sources against frozen Git head3d95aad8, including the
Attention source hint/adapters beyond the original script's own pin list.
profile-one-get.json contains function counts/times only; raw pstats stays in
the owned Temp directory. profile-runner.py.txt reproduces the optional single
GET diagnostic. This task did not modify product, tests, documentation or Git.
