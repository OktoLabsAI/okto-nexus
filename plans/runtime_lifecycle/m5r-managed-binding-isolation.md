# M5r: managed adapter failure isolated across Connector bindings

The local Connector execution owner had two approved bindings on one control connection. For each managed adapter (Codex, Pi and Claude), the first binding opened a session. The second binding then hit a synthetic native preparation failure before process creation. The Connector published a terminal, no-effect receipt for that opening without stopping the first binding's native peer or the shared control connection. The first session still accepted a turn, and a later opening on the second binding succeeded.

This extends the existing same-binding startup-containment check to distinct binding IDs. It exercises the real Core journals and Connector execution owner with synthetic native peers; it does not claim real provider execution or a separate-host Connector. The startup and session-containment suites passed in source and isolated installed environments: 13/13 each. No production code or global Nexus process changed.

Remaining M5 differential acceptance is reconnect, revocation and preserve-agents reset across embedded and local Connector. The physical remote-host qualification remains separate.
