# M3n — Pi version-probe budget, installed UI qualification

Date: 2026-10-17. Branches: Nexus `feature/v0.3.1`, Core
`feature/v0.0.12`, Connector `feature/v0.0.10`. No global rollout.

The production Nexus on port 8202 was not stopped, reinstalled, or faulted.
An installed Nexus 0.3.1/Core 0.0.12 fixture on loopback port 8204 used a new
home and workspace under `build/runtime-m4-real-ui`. The real local Pi 0.87.1
Node bundle was selected from the Agents connection wizard.

The first installation verification failed with `Native version probe exceeded
its deadline`; retry passed with the same installation. Direct `node cli.js
--version` took 2.593 seconds against a three-second Core budget. The first
connection test then failed in `Connecting to harness` with `CONFIG_ERROR`.
Its disposable Core journal has an `OUTCOME_UNKNOWN` open, no native birth,
and a fenced producer with `CONTAINER_STOPPED`. The UI does not reveal the
underlying `CONFIG_ERROR` subtype, so the pre-transport Pi version probe is a
strong path-based diagnosis rather than a captured exception from that test.

Core's owned Pi version observation now allows ten seconds; Claude/Codex and
the generic helper stay at three. Three source tests and three tests against
the rebuilt, isolated, installed Core wheel passed. Wheel SHA-256:
`004a9472140bf2b89c1820281ba7c4a9a658a924adc0fe1e4fcdec749059f8b5`.
The disposable environment imported the wheel from site-packages and
`pip check` passed. Both consumer repositories vendor this exact wheel; Nexus
also updates its vendor manifest hash.

After a normal drain/resume of the disposable server with that wheel, retrying
the same connection test through the UI reached `Connection verified`: the
real model replied, and the temporary Core session closed. Saving the
connection showed `m4-pi` as `Local · Online` in Agents. A first Meta-harness
message returned a Pi reply and `1/1 ack`; its input, tool action and final
text were visible in the live terminal. A second message in the same session
also returned a Pi reply and `1/1 ack`. Pi sent an explicit Nexus message and
a final runtime result on both turns, so the timeline showed two reply cards
per turn. This campaign verifies delivery and outcome; it does not classify
the duplicate replies as a server fanout bug.

The first Meta-harness message was submitted at 16:49:03 local UI time; its
session became ready at 16:51:45 and its turn completed at 16:52:07. The
roughly 162-second cold-session readiness delay remains open M3/M7 work.
The second turn in the existing session was much faster. The exact cold-start
phase breakdown has not been measured, so it is not attributed solely to the
version probe. UI-A and the full three-provider/Connector scenarios remain
pending.

The same disposable home was drained normally with no remaining resources or
error codes and resumed once more with its saved connection. The HTTP owner
became `RECOVERY_READY`, then published `RECOVERY_AGENT_READY` without manual
Recover. Agents showed `m4-pi` as `Local · Online` in the existing browser.
A post-restart Meta-harness message then returned `M4_PI_RESTART_OK` with
`1/1 ack` in the same browser, without changing the connection configuration.
The owner initially recorded `m4-pi` blocked at 19:59:43.532 UTC and cleared
that fence at 19:59:45.699 UTC. The final disposable run drained with no
remaining resources or error codes at 20:04:13.375 UTC; its port listener and
test browser were closed. This is one local Pi restart sample, not the full
UI-A recovery gate.
