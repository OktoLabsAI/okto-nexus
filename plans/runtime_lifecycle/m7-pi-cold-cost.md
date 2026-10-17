# M7 — Pi cold-open verification cost sample

Date: 2026-10-17. Disposable installed Nexus/Core fixture from M3n; global
Nexus on port 8202 untouched. This is a read-only microbenchmark against
the same real local Pi 0.87.1 installation selected through the UI, using
the isolated installed Core wheel after M3o.

The Pi dependency closure contains 14,097 entries. Three consecutive calls
to `launch_artifact_signature` took 1.864, 1.290 and 1.451 seconds. A full
`pi_build_identity` call took 13.185 seconds and matched the selected build
identity. `selected_fingerprint` took 0.913 seconds and matched the selected
fingerprint. These calls used no model/provider request.

Core `prepare` calls `prepare_launch`, which recomputes the full build identity;
Core `open` calls `prepare_launch` again, then `verify_prepared`. Thus two full
identity passes alone cost about 26 seconds on this installation at the
measured rate, before the native harness starts. The bridge also validates
the stat-only closure at several launch frontiers. This is consistent with
the observed 42-second post-restart open, but not a complete attribution of
that sample or the earlier 83-second successful open. Disk/cache load and
other host stages were not independently timed.

Next M7 work: trace the actual per-open call counts and frontier durations,
then retain one full content validation at a safe pre-spawn boundary while
avoiding duplicate work within the same admitted opening. Tests must show
that a changed Node binary, CLI, dependency file, workspace target or lease
still refuses before process birth. A simple time-based cache or increased
deadline is not an acceptable replacement for identity validation.
