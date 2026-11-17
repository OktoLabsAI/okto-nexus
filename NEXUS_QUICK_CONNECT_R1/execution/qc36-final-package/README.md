# QC36 final installed cut

Source freeze: `9bc4034663ca63cfee43790b4bc03c38f8bdebcc`. The new isolated prefix is `nexus-qc-r1-package-i4u7k1l1`; previous prefixes were retained untouched. Nexus wheel SHA256: `d2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88`.

Build, installation, base/local dependency gates, smoke, Twine, pip-check and installed audit passed. Nexus now has **733** payload files because `quick_connect_render.py` was added. Unchanged Core/Connector contribute 168/127, for **1,028** exact installed/wheel payload files. All 1,804 pinned source inputs remained unchanged. The frozen frontend payload was reused, without a Vite rebuild. See `qualification.json`, `READY.json` and `package-manifest.json`.

The orchestrator uses host Python with psutil; pytest itself runs the exact installed prefix with `-I -B`, closed stdin PIPE, own HOME/provider-home/cache directories, sibling CWD/TMP and copied tests/helpers without `src`. No package was added after READY. A metadata-only probe established that psutil is absent from the product prefix; it was not installed there.

This owner's installed shard 0 completed **164 PASS / 8 SKIP / 0 FAIL**, with all 172 collected nodes finished and zero remainder. The skips are three POSIX filesystem cases on Windows and five real-PTY cases under closed PIPE. The three explicitly selected legacy nodes completed **3 PASS**, including exact canonical shortcut, one observed harness and two distinct harnesses. Reports, JUnit, per-phase records, copied-test hashes and physical cleanup are under `installed-shard-0/` and `installed-legacy/`. Shard 1 and shell echo qualification have separate owners/reports; this document does not infer their outcomes.

Both runs preserved 1,028 payload files and source pins with zero drift, exited 0 naturally and sent no signals. Recorded process births, current own-root processes and their listeners were absent at cleanup. Sampling every 0.25 seconds cannot inventory every short-lived child; no exhaustive child-history claim is made. The origin guard verifies pytest and all loaded application/Core/Connector modules at startup and finish. Nested subprocess commands are unchanged and require their own provenance; parent origins alone do not qualify every child.

All fixture actors/Test/version boundaries are synthetic/inert. No provider, paid inference, personal authentication, release, upload or personal installation was exercised. Earlier full-suite failures, skipped PTY/POSIX cases and earlier package cuts remain distinct evidence.
