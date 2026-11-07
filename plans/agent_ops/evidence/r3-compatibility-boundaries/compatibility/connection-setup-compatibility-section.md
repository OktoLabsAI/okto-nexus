## Connector and Server version compatibility

The Connector checks the public `/v1/connections/protocol` contract before using
R4 execution. This check requires the advertised Core version to equal the Core
installed with that Connector, in addition to the management revision, protocol
major, snapshot format and advertised R4 support. Equal wire revision names alone
do not make different Core package versions compatible.

The following exact pairs have been checked through the installed Connector's
`NexusHTTPClient.r4_protocol()` and the installed Server's public HTTP endpoint:

| Connector / its Core | Nexus Server / its Core | Public protocol result |
| --- | --- | --- |
| 0.0.11 / 0.0.13 | 0.3.2 / 0.0.13 | Compatible |
| 0.0.11 / 0.0.13 | 0.3.3 / 0.0.14 | Refused: `VERSION_INCOMPATIBLE` |
| 0.0.12 / 0.0.14 | 0.3.2 / 0.0.13 | Refused: `VERSION_INCOMPATIBLE` |
| 0.0.12 / 0.0.14 | 0.3.3 / 0.0.14 | Compatible |

Both crossed pairs refuse at stage `protocol`, with `possible_effect=false`.
The compatibility check sends one uncredentialed GET and does not register an
executor, issue a ticket or grant, create a binding/session, or submit work.
Use an explicitly coordinated compatible installation when a pair is refused;
do not bypass the version check or downgrade an existing database to obtain a
connection. Connection attempts do not authorize implicit upgrades or stopping
current work.

“Compatible” here qualifies public protocol negotiation, not authenticated
execution, provider credentials, daemon lifecycle, remote TLS or a two-host
deployment. The historical artifacts were built from Nexus
`c1e78e26fb2bd57ace3370417a2cb7529856b603` and Connector
`a3017d97b6a295cb2b46b9dd391b4c04ed121ee2`; the qualification manifest pins all
wheel hashes, including the current 0.3.3/0.0.12 artifacts.

This R4 check is separate from external MCP client compatibility. New
[terminal coordination](terminal-coordination.md) features require their
advertised receipt/passive-observation capabilities and refuse Servers lacking
them; they do not silently fall back to unsafe legacy replay. The table does not
claim to qualify specific external Claude/Codex client versions.
