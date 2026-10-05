# R4 execution evidence

The current source of acceptance is the
[execution ledger](../../plans/r4_execution/acceptance_inventory.json), with
[implementation history](../../plans/r4_execution/IMPLEMENTATION_STATUS.md) and
the fixed [delivery plan](../../plans/r4_execution/DELIVERY_PLAN.md).
Earlier entries in the history are dated observations; later evidence may
supersede their remaining-work notes. Do not add overlapping test counts.

| Installed campaign | Proven scope |
|---|---|
| [NS15.03 boundary](../../plans/r4_execution/M12_NS15_03_HELPER_REMOVAL.md) | Duplicate native helpers absent from Server; REST/MCP contract dispatch through Core |
| [NS15.04 restore](../../plans/r4_execution/M12_NS15_04_CONFIG_RESTORE.md) | Atomic owned configuration and offline restore preserving Core journals and uncertain outcomes |
| [Combined consumption](../../plans/r4_execution/M12_NS06_05_COMBINED.md) | Shared logical claim across managed delivery and MCP; synthetic executor integration |

These campaigns do not prove live provider qualification, independent remote
hosts or the complete final operating-system/Python matrix. G0–G3 remain open.
Use the artifact hashes, exact node IDs and limitations in each campaign's
manifest; a passing fixture is not a passing native provider campaign.

The [older capture index](evidence/EV-INDEX.md) is historical evidence for older
implementations. Its results do not transfer to the R4 artifact tuple. Archived
PR remediation totals are not current release acceptance. Credentials, sessions,
endpoints and personal provider homes appearing in historical captures must not
be reused as setup instructions.

Current instructions: [R4 operations](r4-operations.md) and
[migration and recovery](migration-and-recovery.md).
