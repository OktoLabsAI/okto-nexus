# W12 environment snapshot diagnosis

The installed package is intact: both the original snapshot and a read-only, in-memory streaming equivalent exactly match the reviewed candidate. The installed source, package, review, and service context were not changed. No service, provider, or upgrade retry was executed by these diagnostics.

| Observation | Wall seconds | CPU seconds | Candidate match |
| --- | ---: | ---: | --- |
| Original direct snapshot | 77.016 | Not measured | Yes |
| Original snapshot, instrumented | 62.014 | 54.375 | Yes |
| Equivalent 64 KiB streaming snapshot | 1.697 | 1.172 | Yes |

The instrumented original spent 57.755 seconds in reads (50.625 CPU seconds), 0.761 seconds opening files, and 0.174 seconds hashing. It made 880 reads requesting 64 MiB + 1 byte for distribution files. The two distributions contain 880 files and 14,222,336 bytes in total. The extra Python executable read accounts for the difference from the profiler's overall byte/read totals.

The streaming implementation preserves sorted relative names, skipped bytecode, editable rejection, expected payload checks, the 10,000-file limit, the 64 MiB per-file limit with the extra detection byte, the 256 MiB aggregate limit per distribution, and the exact aggregate digest construction. Its maximum returned chunk was 65,536 bytes. The complete snapshot SHA256 in all three observations is `f6f2693d9948bfb1f06095ab7e6828be218463291ef88a2393d8c10042df3674`.

These measurements support replacing the oversized read request with bounded streaming. They do not directly measure allocator behavior and do not establish a filesystem fault. Sequential runs may have different cache or host conditions; the original read CPU cost and unchanged fingerprint provide the useful evidence here.

The historical upgrade apply returned `UPGRADE_ENVIRONMENT_UNAVAILABLE` after about 68.924 seconds overall (about 62.43 seconds between its private stdout file creation and last write). The canonical probe has a 60-second timeout and hides its underlying exception. The measured original snapshot duration is consistent with a probe timeout; the exact exception from that historical attempt is not recoverable from its public result. The source invokes the probe before writing upgrade_pending or changing context; the retained context remained unchanged.

The diagnostic used `-I -B -X utf8` and direct snapshot calls. It is not a successful canonical 60-second subprocess probe. The streaming substitution existed only in diagnostic process memory. It does not authorize retrying the old package or substituting changed payload bytes under the old reviewed fingerprint. A source fix requires its own qualification, package identity, and canonical review/apply path.
