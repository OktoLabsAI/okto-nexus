# M4d4f1: physical directory audit measurement and admission boundary

The installed Nexus 0.3.1 wheel was exercised in a disposable, fully migrated
Server fixture with canonical closed-session metadata and real empty files in
the local journal directory. `tools/benchmark_runtime_directory_audit.py`
creates and removes only a checked child of `build/m4d4f-directory-audit`.
No real harness, production database or global Nexus process was used.

| Retained files | Fixture setup | `audit_files()` | Name batches | SQLite VM steps |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 11.447 s | 0.159 s | 8 | not measured |
| 10,000 | 35.053 s | 1.634 s | 79 | not measured |
| 100,000 | 420.909 s | 27.520 s | 782 | 1,525,805 |

Each name batch held at most 128 entries. The 100k audit used a progress
callback on every SQLite VM instruction, so its wall time is not directly
comparable with the first two uninstrumented runs. Fixture setup includes
Server migration, 100k historical rows, canonical-name backfill and physical
file creation; it is **not** an application startup measurement. The files are
empty: this measures name attribution, not journal recovery or provider work.
An instrumented 1k sanity rerun used 15,263 SQLite VM steps and 0.243 s,
consistent with about 15.3 steps per file at both 1k and 100k.

The directory can change while Nexus is stopped. The Core registry head and
paired host token prove committed creation intent and detect definite partial
restores, but cannot prove the physical directory unchanged across downtime.
Therefore the current trust model does not authorize moving the complete name
scan behind admission. Keep it in startup until an independent durable
filesystem change source or an isolated per-agent physical layout is qualified.
Optimize scan mechanics and per-agent work without relaxing the unknown-file
fence. This scan's measured cost also does not explain the prior nine-minute
Pi recovery; that incident's retained-history maintenance was separately
addressed in M4d2.
