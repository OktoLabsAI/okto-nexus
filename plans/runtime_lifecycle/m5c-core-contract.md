# M5c Core contract checkpoint

Core commit `4e67dc0` on `feature/v0.0.12` defines the negotiated, strictly validated `nexus-startup-refusal-v1` control report for an opening that fails before the initial lease. It binds the original Core no-effect receipt and exact released capacity reservation while requiring the current host to attest that no native owner exists. The report itself does not grant authority; Server acceptance must authenticate the live control channel and validate the canonical pending operation. The generic receipt ticket path remains unchanged.

The built Core wheel is version `0.0.12`, SHA-256 `d59166ba3956c886711604da7e4dfea35f637cb9bfe4965e43b15a9cadc412d2`. Its 162 package files matched the installed tree, and 73 selected control/receipt tests passed under an isolated Python interpreter. Source details and test scope: `../okto-nexus-connector-core/plans/runtime-lifecycle-m5c-contract.md`.

Connector durable report production and replay, Server in-band transaction, lost-ACK and forged-report tests, separate-process differential test, and major UI gate remain pending. The global Nexus installation is untouched.
