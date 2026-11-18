# SI-020 Pi process birth before protocol I/O

The Windows Core CI failure showed Pi answering unsolicited startup extension requests while the durable process recorder was held. The regression now observes creation of the Pi readers during that hold. Both Pi cases failed against the preceding source, including when the recorder was about to report a write failure. This reproduces the ordering error without relying on the child startup duration. [Failing Core CI](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44376836264)

Core `5d1f7c6233a550c60422d71dc042bc396ed4ae2a` retains the process handle immediately after spawning. It records birth before starting the stdout and stderr readers and before sending readiness traffic. A recorder failure still contains the child under the same owned handle and remains an uncertain post-spawn failure. No protocol frame is sent in that case.

The local Core suite passed 72 tests with one platform skip. The installed Core wheel passed 17 process-birth and Pi cases. Nexus passed 18 presentation cases and Connector passed 23 R4 cases with that wheel installed. Both consumers pin the same unpublished Core 0.0.16 artifact, SHA-256 `b6b7061288b536acb64b5afbc3043d7b740e3f70a4c28d715c45c4345d023b36`. The wheel and source archive passed strict validation. The Pi adapter is the only changed package module. [Core CI for the correction](https://github.com/OktoLabsAI/okto-nexus-connector-core/actions/runs/44382184533)

The tests use local protocol peers. Managed native viewer continuity and the production matrix remain open. The Core contract and Nexus schema stay at their preceding revisions. Roll back by restoring the preceding matching Core wheel in both consumers.
