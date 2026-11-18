# S2 control-reader counterpart — prepared only

The failed original remains FAIL_OR_INCONCLUSIVE_PRESERVED. Its transient file
bytes and traceback were not retained; concurrent writes remain a hypothesis.

Only the host polling reader for control/controls.json changes. Missing files or
JSONDecodeError cause another read under the same original 20-second control
deadline and 180-second owner deadline. Each such read records ordinal, marker,
kind, byte length and SHA256 in an own-Temp JSONL; missing files have null length
and hash. No contents are recorded. Other errors still fail immediately. An
invalid JSON read never counts as acknowledgement, and the original deadline
failure remains if no valid matching done marker appears.

The marker is still created exactly once before polling. There is no new marker,
command, report, retry of a publication, TTL, permission, claim, grant, DTO,
protocol or writer change. The writer is not changed to atomic replacement.
Both canonical OBS publications and all browser/table assertions are unchanged.

The wrapper preserves the base driver __file__ and helper/template/preflight
paths. It validates the base manifest and driver, its own exact variant pins,
effective-driver hash and Root gate before allocation, then validates again
after cleanup. R9 source/payload/tool gates remain in the unchanged base path.
Use a fresh cut ID and genuine Root gate; no runtime has been started here.

Root gate additionally binds reader_variant_manifest_sha256 and
effective_driver_sha256. Proposed execution, only after Root review:

    rtk proxy python -B .../reader-v2/run.py --gate .../RUN_READY-S2-reader-v2.json

Existing curator remains applicable to the preserved base run outputs. A
separate derivative curation must include variant before/after and the invalid
read audit count/hashes, preserving original failures. E13 browser meaning is
the target; H08 active-claim coverage remains partial.
