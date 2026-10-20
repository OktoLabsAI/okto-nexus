# M5s: installed differential recovery, revocation and reset checks

Selected existing installed-wheel tests were run without modifying production code:

| Path | Verified behavior | Result |
| --- | --- | --- |
| Embedded Nexus | Preserve-agents reset keeps connection, grant, profile, workspace and MCP preset records; active session drains; fresh turn succeeds; reset rollback keeps immutable history fence | `test_reset_connections.py` and `test_reset_independent_inventory.py`: 10 passed |
| Local Connector over real loopback WebSocket | Active reset stops remote execution, keeps the binding and accepts a new open/turn/close; profile revocation is contained; Graph presence becomes offline after disconnect | Three selected integrated cases passed |
| Local Connector over real loopback WebSocket | Active connection loss retains lease/effect evidence while its owner drains | One selected integrated case passed |
| Embedded Nexus | Native process exit restores without lock reset or replay; revocation with delayed stop retains sibling availability | Four selected cases passed (two process-exit and two revocation variants) |
| Connector unit lifecycle | Disconnect cleanup preserves a live lease; reconnect retains executor identity; revoked binding blocks publication | Five selected cases passed |

This establishes passing slices on both paths, not a paired end-to-end run with the same real provider and fault timing. The integrated remote tests use a real Server/Connector transport with a synthetic native peer. No separate physical host or real UI interaction occurred in this checkpoint. The final M5/UI-B comparison remains restricted to reconnect, revocation and preserve-agents reset with real harnesses and operator-visible status; no new acceptance criteria were added.
