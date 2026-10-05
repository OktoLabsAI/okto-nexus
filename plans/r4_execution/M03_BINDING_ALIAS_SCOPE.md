# Binding alias scope

Nexus 7398130 fixes an existing-endpoint check that rejected additional bindings solely because an agent already had an endpoint for the same workspace and adapter.

Prepare and apply now use canonical agent, executor and workspace scope when checking aliases. The same alias may exist on another executor; a distinct alias may exist on the same executor. An existing alias in the same scope remains a conflict. Legacy endpoints without canonical executor scope still require review.

Tests use public registration, inventory, realization, prepare and apply routes. They verify distinct binding/endpoint IDs, preservation of the original endpoint and unchanged agent identity/credential fields. Authentication's last_seen_at is allowed to advance. Publication tickets remain subject to current authority.

Installed verification: 24 passed. Source verification: 19 overlapping cases passed. The published baseline reproduced two incorrect refusals. The installed campaign also exercises the public Connector CLI over HTTP/WSS, initial child turn and controls on the unchanged Connector/Core pair.

[Artifact hashes, results and limitations](test_runs_20261001_binding_aliases.json).

Explicit rebind/replacement, revision isolation for live sessions and complete alias selection acceptance remain pending. No milestone or release gate closes.
