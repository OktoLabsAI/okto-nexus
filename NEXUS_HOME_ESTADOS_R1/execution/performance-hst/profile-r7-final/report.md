# R7 installed diagnostic — not p95

Three separate HTTP200/ready GETs on a pristine mixed100 seed clone. All owned processes exited normally with no immutability drift.

Fastpath observed: 925 index projections; zero legacy result-attention UDF calls. Batch template 3b32c7fe9bd8c139756570d1fce4a80789702d90e1747813760a0db292052975 contains no correlated result-attention scalar lookup.

First GET: HTTP 1497.949ms; service 1207.710ms; render 4.880ms; outside these scopes 285.359ms. The last quantity is neither pure transport nor pure product cost.

SQL GET: HTTP 918.526ms, execute 270.303ms, fetch 215.358ms. Third GET HTTP 1156.805ms; its profile includes service execution.

| Service function | Calls | Own ms | Cumulative ms |
|---|---:|---:|---:|
| home_entries.py:26 read | 1 | 0.075 | 1205.197 |
| home.py:39 _safe | 4 | 0.019 | 1193.633 |
| home_entries.py:59 <lambda> | 1 | 4.977 | 1193.630 |
| home_entries.py:89 _read | 1 | 2.676 | 1188.652 |
| home_entries.py:407 read | 1 | 25.295 | 705.061 |
| home_entries.py:301 _work_results | 1 | 58.920 | 502.202 |
| home_harness_board.py:65 page | 1 | 42.727 | 390.610 |
| ~:0 <method 'execute' of 'sqlite3.Connection' objects> | 60 | 182.614 | 328.025 |
| attention.py:38 canonical | 8269 | 6.613 | 224.940 |
| __init__.py:183 dumps | 8375 | 17.656 | 218.986 |
| attention.py:42 digest | 6132 | 13.033 | 208.087 |
| encoder.py:183 encode | 8375 | 15.841 | 197.497 |
| encoder.py:205 iterencode | 8375 | 174.811 | 174.811 |
| home_entry_pages.py:247 metadata | 1 | 8.745 | 156.321 |
| home.py:333 activity_item | 1000 | 7.588 | 144.435 |
| home_entry_pages.py:149 revision | 1 | 15.717 | 135.256 |
| home.py:308 result_item | 925 | 13.990 | 129.590 |
| home_entries.py:425 source | 7 | 0.042 | 107.170 |
| __init__.py:299 loads | 7053 | 10.955 | 106.676 |
| decoder.py:340 decode | 7053 | 18.750 | 91.943 |

| SQL template SHA256 | Calls | Execute ms | Fetch ms |
|---|---:|---:|---:|
| 3b32c7fe9bd8c139756570d1fce4a80789702d90e1747813760a0db292052975 | 1 | 191.415 | 159.041 |
| d32123b4d14450d9b0c7baa9f596fba49e8d6319c649f6ef9a9c6703bfa5506e | 1 | 44.817 | 0.004 |
| 9b6d50444f0a458c3213ee3ec19e2f2f4e4152c31b18b711a925c1954595d72b | 1 | 14.256 | 10.248 |
| 1d241c7904da6fc88a471f0dec8abde00e76e79b2a5976d27c3833bdd144de55 | 1 | 13.196 | 2.892 |
| 556c8d009da6c6ff9fea25ed899d48ee34dfa570bb6dcf440a6c0fdf87f33058 | 1 | 0.674 | 12.720 |
| 77c99108835aed34490804dad7a86b147f0c11c8a01215864be693e44a4c886a | 1 | 0.128 | 12.163 |
| 527412ce2e8b25f9818b06fbb50ef5fd744d9befffce63b5f776f264b44928c1 | 1 | 0.094 | 4.251 |
| 33938cc3630f4f661af7e3a695766697b217a1e62e016169702b29ef757440ce | 1 | 0.434 | 2.789 |
| 26afa7c90aa3465370999c01167b7769881062f1e3255ca1ba3ad71b88d199f9 | 1 | 0.791 | 1.715 |
| 354c840431f9250fb21e19c8f27e49cd496d66b542abb0fb8d46740cd66e8f55 | 1 | 0.103 | 2.040 |
| 44b00c3156b4ec4a33a2007bd94340a3e572d9c41544b4563817d4926b406114 | 1 | 0.344 | 1.474 |
| 035e64a78039781a9add8327b2bbc0408954eb80ac01be4da63a14a8d8a6dd73 | 1 | 0.292 | 1.276 |
| a7c8a9cf1bf23d3f0506be30ab9bb4c8eba07acae0f4515a7dcdc630e46a0208 | 1 | 0.106 | 0.814 |
| f10614dede30c7e34d088f56385fbdac9812dc160f8e5e746774bfef08de1920 | 1 | 0.085 | 0.756 |
| c6760d489adb38f2f5653142a366a6bc83f5d43ff48d87aa0787c2c03f12ea70 | 1 | 0.097 | 0.582 |
| ae5cba6fbdcb983d5994f246fe4a1351a08397e090ad44eb83f691967da7fb19 | 1 | 0.091 | 0.563 |
| d1f769f0c5a718eb4b90ddcb4a79ce73e1f22384d5c2b31cd9cd1212d4569817 | 1 | 0.062 | 0.555 |
| f7e1f57123e4df9997e5747ccb28d6ef788d96a481bc568224749ef181c5d9bf | 1 | 0.041 | 0.503 |
| 732a59fbfda7da77a1e15533816ea892b2bfe70db3fde9ae450e835adf4de6ca | 1 | 0.061 | 0.438 |
| d1a54ea78936d6754a36e2e50f6fd349e34456dd06e9774c0be88578ac3a6c1f | 1 | 0.472 | 0.005 |

Three separate GETs, no nested profiler; not p95 samples or an SLO approval.
cProfile cumulative costs and SQL execute/fetch costs include overlapping UDF/projection work; do not add them.
Cold first GET includes routing/auth/import initialization. Third main-loop profile contains service execution itself.
SQL/EXPLAIN preserve original templates only, no bound parameters or expanded SQL. EXPLAIN overhead excluded from execute/fetch.
R7 matrix remains FAIL: candidate five PASS/three FAIL at500ms; baseline two FAIL. DOM remains NOT_RUN.
No source/schema/seed/TTL changes, provider/native authority claim, or attribution of all elapsed time to ASGI.
100ms ancestry polling cannot enumerate every short-lived child; no such completeness claim

Remaining measured costs include the combined Work/Results relation, canonicalization/fingerprints and complete board/page reduction. The lookup fastpath is active; fallback is not the explanation for this cut. No isolated proposed change is claimed to reach500ms.
