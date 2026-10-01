# Passive discovery shutdown and lease watcher completion

Core 8d519e0 / 0.2.48.dev0; Connector d4cb0c2; Nexus 79c2d3f.

## Implemented

The Core discovery facade accepts an optional cancellation callback. It checks between file reads, directory entries and discovery steps. Cancellation raises DiscoveryCancelled without returning a partial inventory. The context is isolated between threads and reset after the call; the build identity algorithm and content coverage are unchanged.

The Connector control owner and the Nexus embedded inventory owner signal cancellation during shutdown. Both retain the reader until it exits. The embedded owner discards discovery completed after stop and retains started publication writes until completion before releasing ownership.

The lease watcher now initializes its pending-event flag even when another route has already fenced the lease. A focused failing test reproduced the former UnboundLocalError. Final checks confirm physical containment and the durable core.lease_closed journal event.

## Installed evidence

| Campaign | Result |
|---|---|
| Core discovery, identity, race, lease and containment cases | 139 passed |
| Connector configuration, control, execution and publication cases | 165 passed |
| Nexus embedded inventory, tools, binding and public integration cases | 89 passed |
| Stronger durable journal assertions for two included Core cases | 2 passed; overlapping coverage |
| Actual daemon stop during Pi discovery | Passed; 0.0144 seconds after stop request |
| Actual normal Pi handoff/rebind journey | Failed at the existing 120-second control-readiness deadline |

The actual stop campaign ended before inventory publication, admitted no runtime operations, returned exit code zero for daemon and Server, and removed its campaign credentials. The normal Pi failure also shut down and cleaned up successfully.

Core SHA-256 is identical in all three repositories: 205b16320ce75c228d54598f05c8b6286ee2c202bf1ef87ff247da4b696d62a0. Package/source/installed bytes were compared. pip check, local-wheel lock validation and both contract-generation checks passed.

The source-stage fixture failures, former watcher exception, first Nexus wheel and failed normal Pi campaign are preserved in the [manifest](test_runs_20261001_discovery_stop.json).

## Measured remaining work

An installed passive-discovery profile took 66.18 seconds for Pi 0.87.1. Opening files consumed 55.87 seconds; the identity covered 14,097 entries. Its qualified build identity was sha256:caf8bfad84ea26a7c8eaee06e0cde3dd7e34ef05e00dbebc348dfb3f22de487b.

The next M11 work is to reduce the measured file-opening cost while retaining full content verification, identical manifest order, bounded resources and cooperative shutdown. Startup must pass the existing readiness deadline before this provider journey is accepted. The profile does not establish the cause of all observed timing variation.

This increment does not close NS14.03 or M11. A complete shared shutdown deadline, per-resource DRAINING_PENDING report, retained recovery loop, second recovery, Linux, separate hosts and final provider qualification remain pending. All gates remain open.
