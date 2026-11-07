# Protected terminal helper — revision 4

This revision changes only the ordering of progress updates immediately after a
successful producer spawn and consumer Popen. Each start and its possible effect
are recorded before querying process identity. A failed identity query can no
longer report that an already-started process was never started. Containment,
canonical marker parsing, cooperative delivery, environments and deadlines are
unchanged from revision 3.

The current qualification is **3/3 PASS**: two injected identity-failure boundary
models (no actual process in those two cases), and one real benign ConPTY
cooperative transfer. The latter proves that the consumer starts while the
producer waits, three streams are TTYs, no console window is visible, material is
transferred privately once, both processes exit0, and the owned Job is empty
without forced cleanup. No product CLI, service, provider or real credential ran.

The seven revision-3 cases remain historical evidence. They include installed
sink/parser functions, ambiguity before/after delivery, deadlines and nonzero
consumer exit. They were not rerun or relabeled as revision-4 executions. The
entire prior public curation is retained unchanged under `history-public-v3`.

Use the original `revision-4/protected_pty.py` with its adjacent `owned_job.py`.
The dependency still resolves to the original parent's isolated
`venv/Lib/site-packages` (`pywinpty==3.0.3`, exact pinned wheel). The public source
copy is evidence, not a relocated runnable dependency installation.

API remains `transfer_once(producer_argv=..., consumer_argv=..., env=...,
consumer_env=..., cwd=..., timeout_seconds=120, synthetic_probe=False)`.
Authorization/proposal hashes, approved argv and external service ownership are
caller responsibilities. No retry is performed. `synthetic_probe=True` is only
for these benign producers. The Job must never contain a persistent service or
productive session; only auxiliary CLIs and finite probes are in scope. The
complete IO/privacy/deadline and Scheduler integration limits are retained in
`history-public-v3/README.md`.

Reproduce with a new output directory:

```powershell
rtk proxy C:/Python313/python.exe -I C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97/revision-4/qualify.py new-run
```

The manifest is a finite public allowlist. It excludes environments, synthetic
homes, secret material, transcripts, wheel binaries and pycache.
