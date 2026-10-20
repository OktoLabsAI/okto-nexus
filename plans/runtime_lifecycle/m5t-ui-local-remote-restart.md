# M5t: real Pi UI delivery after Nexus and Connector restart

The disposable Nexus home at `build/runtime-m6d-ui/home` ran installed Nexus 0.3.1 at `127.0.0.1:8204`; its separate local Connector used installed Connector 0.0.10 and Core 0.0.12. The global listener at 8202 remained stopped. At first, Agents showed remote `m6d-pi` Offline and embedded `m5l-pi-new` and `m5m-pi-new` Online. After starting only the retained Connector daemon, Agents showed `m6d-pi` Remote · Online / Connected without restarting Nexus.

Through the Meta-harness UI, the operator sent two new private messages in workspace M6D, asking the real Pi harnesses to return exact markers without modifying files:

| Route | Message | Durable result | UI response |
| --- | --- | --- | --- |
| Remote Connector, `m6d-pi` | `msg_dc9a0a41d360490aade8a8a76867a99f` | delivery read; outbox `op_086c6df77cd046c2ba789c61d7c43e6b` ACCEPTED / NATIVE_ACCEPTED | 1/1 ack; exact `M5T_REMOTE_OK` |
| Embedded, `m5m-pi-new` | `msg_e280856c79e042fba0d2c7906e7dfae4` | delivery read; outbox `op_6d52061c555b4a0da895c10123e3e393` ACCEPTED / NATIVE_ACCEPTED | 1/1 ack; exact `M5T_LOCAL_OK` |

The browser observation and read-only SQLite check agree. This verifies the restart/reconnect delivery slice with real Pi on both paths. No fault was injected during these two messages, and this is not a reset/revocation comparison or latency distribution. Those remain fixed M5/UI-B items.
