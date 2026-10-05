# Canonical binding and operator inventory reads

The packaged UI audit found that the normative binding-read route was missing
and runtime-options incorrectly refused an operator inspecting another agent.
This change implements those backend prerequisites for the full R4 UI journey.

`GET /v1/connections/bindings/{binding_id}` now authenticates the current
subject/operator inside the same transaction as the read. The closed BindingView
contains current binding/realization references and revisions, not an old apply
reply. It projects APPROVED, DISABLED, PENDING_REVIEW, STALE and REVOKED from
canonical records. An offline executor does not erase binding consent; APPROVED
does not imply technical eligibility or an execution grant. Reads synchronize
agent revision counters like `/connections/me`, including an inactive subject
observed by an operator. They never create grants, operations, sessions or outbox
work and do not resolve local/remote provider files.

Inventory and runtime-options reads revalidate the actor credential within their
transaction. Operators may inspect another existing subject. A non-operator may
read its registered executor or an executor reached through its enabled, approved
canonical binding. An unrelated agent cannot use an agent ID hint or binding ID
to obtain another subject's projection. The inventory remains the original
executor/Core projection and is not requalified using the Server's OS.

Initial source tests exposed two fixture mistakes (a nonexistent grant table name
and UPDATE against an absent method row); both are preserved in the initial JUnit.
The corrected binding/revision/replacement selection passed 29 tests, and the
binding/operator inventory/NS04 selection passed 20. Installed verification then
passed **37 tests in 101.91 seconds**, including these reads, binding replacement,
NS03 revisions, NS04 inventory and packaged OpenAPI. The runner verified all
installed Nexus/Core/Connector bytes against their wheels and recorded unchanged
campaign inputs. Dependency compatibility checks passed. See
[campaign](evidence/binding-inventory-views/installed/campaign.json),
[installed hashes](evidence/binding-inventory-views/installed/installed.json) and
[JUnit](evidence/binding-inventory-views/installed/tests.xml).

Remaining M10/NS13 requirements include effective workspace-aware eligibility,
inventory refresh, executor/installation/workspace selection, reviewed consent,
start/reuse/control and native decisions through the actual UI, plus US English
and packaged-browser acceptance. This backend increment does not close M10,
NS13, M13 or G0–G3.
