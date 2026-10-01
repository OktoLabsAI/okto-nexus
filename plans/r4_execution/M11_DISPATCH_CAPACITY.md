# NS14.04 dispatch selection and retained uncertain capacity

## Reproduced defects

The previous dispatcher selected at most 32 pending operations, ordering all controls ahead of productive work, and only then checked quota eligibility. A backlog of blocked controls could therefore hide an eligible productive operation. Oversized entries could also hide a later control that fits.

The usage query counted RESERVED and SENDING rows but omitted RECONCILING rows. Connection-loss recovery deliberately retains the latter's exact reservation token and byte cost because delivery may have occurred. Omitting those rows allowed new reservations to reuse capacity without a release proof.

Five directed cases failed against the preceding installed Nexus wheel. The initial XML is retained.

## Correction

Selection now queries control and regular lanes independently, filters by their remaining byte budget before selecting the earliest eligible row, and skips a lane whose item budget is full. Each query returns at most one row. The stored semantic payload's UTF-8 cost is measured in SQLite with length(CAST(... AS BLOB)); reservations keep that exact cost and token. Ineligible rows remain durable. Control priority and pre-send authority revalidation remain in force.

RECONCILING rows continue to count against both item and byte capacity until the durable resolution releases their reservation. No timeout or connection change donates that capacity.

Six directed cases cover full control item capacity, full control byte capacity, 40 oversized controls ahead of productive work, uncertain regular item/byte reservations, and a fitting control after oversized rows with an exact multibyte UTF-8 cost. They use actual SQLite and a canonical admitted opening, then seed synthetic scheduler backlog rows; they do not claim native delivery of those synthetic rows.

## Installed verification and remaining scope

The runner compares source/wheel/installation bytes for Nexus, Connector and Core, then tests Connector execution/admission and Nexus reservation ownership, canonical controls, initial turns, native decisions and embedded dispatch. Exact results and hashes are in test_runs_20261001_dispatch_capacity.json.

NS14.04 remains partial. This change corrects dispatch eligibility and uncertain capacity accounting. The full normative flood/control load case, pending admission limits before operation creation, fair progress across executors and aggregate metrics remain unqualified. No release gate is closed. Core and Connector artifacts are unchanged, and preexisting UI assets are not accepted by this increment.

## Regression fixture corrections

The broader installed candidate passed 79 Nexus cases and failed two control cases at an old HTTP 400 assertion. The normative HTTP contract specifies 422 for malformed targets. After correcting it, the close variant reached an old SUBMITTED assertion; the installed Core explicitly returns SUCCEEDED after R4 close completion. Both expectations were updated to the current contracts. A final installed 13-case controls follow-up passed, including cancellation, same-operation close replay, one native close and failed close-projection recovery. The union is 81 Nexus plus 53 Connector cases; this is incremental qualification on the same wheel, not a claimed clean rerun of the entire campaign.
