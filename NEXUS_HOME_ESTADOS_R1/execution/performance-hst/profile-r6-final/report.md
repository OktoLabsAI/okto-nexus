# R6 installed diagnostic — not p95

Three separate persistent-ASGI GETs completed HTTP200/ready on a pristine original mixed100 seed clone. No nested profiler, product change or timing-target waiver. All owned processes exited normally; no remaining listener, force, timeout or immutability drift.

First GET: HTTP 1744.346ms; service 1394.737ms; render 3.389ms; outside those scopes 346.220ms. This last quantity is not all transport or all product.

Second GET: SQL execute 270.785ms plus fetch 246.250ms (UDF/projection work overlaps). Third GET HTTP 1174.948ms; its main-loop profile includes service.read itself, so do not call the event-loop total external overhead.

| Service function | Calls | Own ms | Cumulative ms |
|---|---:|---:|---:|
| home_entries.py:26 read | 1 | 0.091 | 1394.207 |
| home.py:39 _safe | 4 | 0.021 | 1372.463 |
| home_entries.py:59 <lambda> | 1 | 4.518 | 1372.458 |
| home_entries.py:89 _read | 1 | 2.568 | 1367.940 |
| home_entries.py:328 read | 1 | 22.449 | 844.868 |
| home_entries.py:267 _work_results | 1 | 65.905 | 613.316 |
| home_harness_board.py:65 page | 1 | 26.959 | 422.060 |
| ~:0 <method 'execute' of 'sqlite3.Connection' objects> | 60 | 225.313 | 354.125 |
| attention.py:38 canonical | 12253 | 10.906 | 349.511 |
| __init__.py:183 dumps | 12359 | 33.277 | 339.654 |
| encoder.py:183 encode | 12359 | 26.080 | 299.881 |
| home_entry_pages.py:233 page | 1 | 11.401 | 265.321 |
| encoder.py:205 iterencode | 12359 | 262.259 | 262.259 |
| attention.py:42 digest | 7264 | 16.977 | 261.115 |
| home_entry_pages.py:149 revision | 1 | 18.718 | 214.689 |
| home.py:308 result_item | 925 | 21.101 | 196.384 |
| __init__.py:299 loads | 7978 | 13.658 | 133.476 |
| home_entries.py:346 source | 7 | 0.051 | 130.608 |
| home.py:333 activity_item | 1000 | 6.652 | 127.733 |
| decoder.py:340 decode | 7978 | 23.547 | 114.978 |

| SQL template SHA256 | Calls | Execute ms | Fetch ms |
|---|---:|---:|---:|
| 2e2e8a17fbf1f38204d9d4e6214f6db6ddc43d2979180c88190bd1e3e04dd496 | 1 | 198.611 | 202.225 |
| d32123b4d14450d9b0c7baa9f596fba49e8d6319c649f6ef9a9c6703bfa5506e | 1 | 39.266 | 0.008 |
| 9b6d50444f0a458c3213ee3ec19e2f2f4e4152c31b18b711a925c1954595d72b | 1 | 16.598 | 10.988 |
| 1d241c7904da6fc88a471f0dec8abde00e76e79b2a5976d27c3833bdd144de55 | 1 | 11.587 | 2.694 |
| 77c99108835aed34490804dad7a86b147f0c11c8a01215864be693e44a4c886a | 1 | 0.094 | 10.852 |
| 556c8d009da6c6ff9fea25ed899d48ee34dfa570bb6dcf440a6c0fdf87f33058 | 1 | 0.442 | 7.355 |
| 33938cc3630f4f661af7e3a695766697b217a1e62e016169702b29ef757440ce | 1 | 0.415 | 2.695 |
| 527412ce2e8b25f9818b06fbb50ef5fd744d9befffce63b5f776f264b44928c1 | 1 | 0.089 | 2.601 |
| 26afa7c90aa3465370999c01167b7769881062f1e3255ca1ba3ad71b88d199f9 | 1 | 0.530 | 1.061 |
| 354c840431f9250fb21e19c8f27e49cd496d66b542abb0fb8d46740cd66e8f55 | 1 | 0.057 | 1.172 |
| 44b00c3156b4ec4a33a2007bd94340a3e572d9c41544b4563817d4926b406114 | 1 | 0.229 | 0.909 |
| 035e64a78039781a9add8327b2bbc0408954eb80ac01be4da63a14a8d8a6dd73 | 1 | 0.212 | 0.877 |
| f10614dede30c7e34d088f56385fbdac9812dc160f8e5e746774bfef08de1920 | 1 | 0.037 | 0.465 |
| ae5cba6fbdcb983d5994f246fe4a1351a08397e090ad44eb83f691967da7fb19 | 1 | 0.055 | 0.405 |
| d1f769f0c5a718eb4b90ddcb4a79ce73e1f22384d5c2b31cd9cd1212d4569817 | 1 | 0.045 | 0.412 |
| c4a3c65b1e6e6669aa77ee2f3054d9d3b1e216248fb6b7603b2e380c3295b7a9 | 1 | 0.447 | 0.001 |
| a7c8a9cf1bf23d3f0506be30ab9bb4c8eba07acae0f4515a7dcdc630e46a0208 | 1 | 0.043 | 0.377 |
| d1a54ea78936d6754a36e2e50f6fd349e34456dd06e9774c0be88578ac3a6c1f | 1 | 0.337 | 0.003 |
| 732a59fbfda7da77a1e15533816ea892b2bfe70db3fde9ae450e835adf4de6ca | 1 | 0.039 | 0.291 |
| 5d0b0130edcbfebca0e09a0e6727d331316a6120ea4b4177fe90e19c47641d99 | 1 | 0.065 | 0.256 |

Each diagnostic GET is separate, not nested profiling, not a p95 sample and not a new SLO PASS.
cProfile cumulative times and SQL UDF execute/fetch times overlap; do not add them.
First GET includes cold routing/auth/import initialization. Third GET includes service execution in the main event-loop profile; await/select wall cost is not independent CPU cost.
SQL plans contain templates only, no bound parameters or expanded SQL; EXPLAIN instrumentation overhead is separate from execute/fetch timers.
The final10 measurement verdict remains FAIL for all six100-connection cuts. No optimization or threshold change was performed.
100ms ancestry polling cannot enumerate every short-lived child; no such completeness claim

Primary measured candidates for Root review: combined Work/Results read (~401ms execute/fetch in the separate SQL GET), canonical serialization/fingerprints (12,253 canonical calls;7,264 digests under service cProfile) and full relation/page processing. JSON response rendering itself is small. No claim is made that any isolated change will reach500ms; the raw top100 functions and SQL templates/EXPLAIN are preserved in the diagnostic JSON.
