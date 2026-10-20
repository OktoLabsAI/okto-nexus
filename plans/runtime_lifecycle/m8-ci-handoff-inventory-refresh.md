# M8 installed CI: handoff selection inventory refresh

Run [39451295539](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39451295539) on `28f82a0` passed the Claude approval sequence in Ubuntu 3.12 shard 1 and reached the handoff executor-selection file. Its `busy_affinity` case failed before submitting any runtime operation: `runtime.start` resolution returned only `inventory_not_fresh`. The fixture had confirmed both live Connector inventories immediately before yielding, but the selected publication marker can change between that check and the next resolution request.

The fixture now retries only this no-effect blocker for at most 20 seconds. Because a refused intent is durable, each attempt uses a distinct client intent ID; any other blocker or HTTP failure still fails the test. The exact case passed locally on Linux Python 3.12 against the pinned installed Nexus, Core and Connector wheels. Product code is unchanged. A complete installed matrix is still required.
