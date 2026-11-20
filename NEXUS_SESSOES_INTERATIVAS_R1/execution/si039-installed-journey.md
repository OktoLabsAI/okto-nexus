# SI-039 installed Nexus, Connector and Core journey

A fresh Windows virtual environment installed Nexus 0.3.8 with `serve-lite`
and the pinned Connector 0.0.15 and Core 0.0.16 wheels from the offline cache.
Both consumers require the same Core version. The verifier compared all
1,145 hashed installed package files with the three wheel RECORDs, validated
the Core R4 manifest and passed the dependency and offline lock checks.
Product, frontend, pins and lock inputs match the Nexus wheel build.
[Package digests, baseline and observations](si039-installed-journey.json)

The installed Connector daemon negotiated R4 over a real loopback WebSocket.
The production Nexus HTTP app served the JavaScript and CSS byte for byte
from the installed wheel. The Pi 0.87.1 process used a deterministic extension
in an isolated profile with external network calls blocked.

1. One work request started a turn on the reviewed Pi connection. The
   installed `session list` command found the exact session by the confirmed
   binding and workspace.
2. An authenticated Edge browser opened the exact scoped conversation in
   operational Home. Active showed the collaborator, and the conversation
   showed one copy of the prompt.
3. The installed `session attach` command opened the read-only Pi transcript
   in Windows ConPTY. Ctrl+C returned the exact detach receipt and restored
   the console modes. The attachment was durably detached, and the original
   Pi process was still alive.
4. The fixture released the held response. The browser showed one copy in
   the same conversation and the CLI listed the same session again. The
   native history contained one user message, and the database held one open,
   one submitted turn and one result. A canonical close retired the session
   and the native process exited.

The final browser/CLI journey and 61 installed regressions passed. A separate
live HTTP/MCP smoke passed with two authenticated agents, 54 tools and a
confirmed canonical Server stop. Earlier attempts corrected a URL comparison,
a terminal-read readiness race and a cleanup check that still expected a
synthetic process. One earlier test runner was stopped after its native
session had already closed canonically. The final run completed its normal
cleanup.

This covers integration and installed-package verification for SI-T-I05 on
Windows loopback. It used a fixture operator vault, approved candidate
selection and synthetic model responses. Real-provider campaigns,
cross-machine verification and human acceptance retain their existing gates.
The increment changes evidence and the ledger. Reverting the commit removes
those records without a runtime or database rollback.
