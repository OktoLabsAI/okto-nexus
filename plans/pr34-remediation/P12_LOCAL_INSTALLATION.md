# Local 0.2.0 installation and installed-package qualification

Implementationff905c433e1a92ae35993b2189919f75ad07dd51. The corrected Windows
full suite terminated exit0 before installation:2637 PASS/121 SKIP. Linux full
regression subsequently terminated exit0:2714 PASS/44 SKIP; see P12_FINAL_AUDIT.md.

The uv-managed global installation was upgraded from0.1.10 to0.2.0 using the
explicit corrected wheel, SHA256
`f99a9f733fd7cabfa5b09dd6f5379f8c5d21e849c5cf1ff1fdb1303a6237e4b5`.
Immediately beforehand, a read-only exact executable/tool-directory census found
no running process using that installation; free space checks passed. No process
was terminated. Python3.13.1 and the existing `serve` extra were retained.

The installer constrained every other installed dependency to its observed
version and resolved offline with existing caches. Only Nexus was uninstalled
and replaced; all69 other dependency versions remained unchanged. `uv pip check`
passed. Every one of267 package files exactly matched its wheel entry, including
the corrected inbox implementation,64 migrations and freshly built dashboard.
The installation does not contain the unrelated local generated asset edits.

Exact argv, dependency versions, free-space observations and results are in
[evidence/p12-installed-release-ff905c4.json](evidence/p12-installed-release-ff905c4.json).
The installation command was `uv tool install --force --reinstall-package
okto-nexus --python <existing base interpreter> --constraints <observed pins>
--no-python-downloads --no-config --offline "okto-nexus[serve] @ <explicit wheel URI>"`.
Private launcher `.git/pr34-evidence/install-corrected-release.py` records its
hash and exact paths. Re-running it blindly is intentionally rejected once the
pre-install version changes; a future update requires a new preflight.

## Installed-package checks

Both checks used the installed tool interpreter, fresh HOME/USERPROFILE/TEMP on
D, a minimal environment without PYTHONPATH/provider keys, and a working directory
outside the repository. No personal Nexus database or model configuration was
opened or migrated.

1. `scripts/live_client.py`: exit0, `LIVE E2E RESULT: PASS`. Actual installed MCP
   subprocess, initialization, two-agent coordination, message/event, handoff,
   artifacts and shared markdown flow.
2. `runtime_comparison_benchmark.py --installed --samples 5`: exit0/PASS. This
   optional mode injects no source path and verifies the bootstrap import lies
   inside the expected installed tool root. Actual production HTTP/owner uses
   feature ON and required authentication; an invalid credential is denied.
   An approved temporary profile/endpoint opens one synthetic Codex protocol
   subprocess, exercises ten turns (five warmup/five recorded), obtains durable
   correlated results and observes that owned process stopped on shutdown.

The second check is an installed integration smoke, not a new native-provider or
performance claim. The optional script mode changes no product code, controls,
contracts or default source benchmark behavior. Real Codex/Claude qualification
is in P12_NATIVE_FRAMES.md; Pi and dedicated attach remain NOT_RUN.

Raw logs stay private. The sanitized manifest contains no credentials or prompt
transcripts. Global `okto-nexus` now resolves to the installed0.2.0 executable;
no background personal server was started as part of the update.
