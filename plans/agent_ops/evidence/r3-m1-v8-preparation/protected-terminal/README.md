# Protected terminal helper — revision 5

Three focal synthetic cases passed. The helper now accepts optional
`consumer_ready_marker`, retaining the canonical key block in memory while
continuing to drain the producer. When configured, it starts the consumer once
only after the exact complete public marker line appears. Missing or divergent
markers cannot trigger delivery. Existing ambiguity, deadline, owned Job and
no-replay behavior remains intact.

For this campaign the caller must first require the handoff path absent, then
pass `consumer_ready_marker='Host handoff (contains no key): '+str(handoff)`.
The installed Nexus handoff sink prints this line after atomic_json. The helper
does not replace the Connector's canonical content/scope validation. The optional
default preserves the previous helper behavior and is insufficient for this
remote setup unless the caller supplies the marker.

The positive fixture calls the installed material_sink and handoff_sink directly
with fictitious material and an own temporary public handoff. It deliberately
prints the key first, delays creating the handoff, then announces it and waits
for the consumer. The consumer reads the handoff before stdin, matching the
ordering that exposed the bug. The report confirms the helper observed the key
before the readiness marker, then delivered once, with both children exit0 and
an empty Job. The absent-marker deadline and divergent-marker cases both retain
possible producer effects but record zero consumers and zero delivery attempts.

No product CLI, service, provider, account or real credential was used. These
fixtures do not validate the full canonical handoff schema or authenticate an
identity. Earlier seven V3 cases and three V4 cases remain historical; they were
not rerun or promoted to V5 executions. The original independent review finding
is preserved unchanged; review-addendum.json describes only this correction.

Use the original revision-5/protected_pty.py with adjacent owned_job.py. Its pinned
pywinpty dependency remains in the parent's isolated venv. Public source copies
are evidence, not a relocated runnable dependency installation. All earlier
ownership/privacy/deadline limits remain applicable: the Job may contain only
auxiliary CLIs and finite probes, never persistent services or productive turns.
The caller still owns authorization, exact argv/pins and external service checks.

Reproduce only these benign cases with a new output directory:

```powershell
rtk proxy C:/Python313/python.exe -I C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-5/qualify.py new-run
```

The public manifest is an explicit allowlist and excludes homes, raw terminal
streams, fictitious keys, environments, wheel binaries and pycache.
