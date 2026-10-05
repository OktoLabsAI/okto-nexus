# M3 reviewed legacy endpoint adoption

BindingPrepareRequest now accepts the optional adopt_endpoint_id for an operator
adopting a catalog-migrated local endpoint. It is mutually exclusive with
replace_binding_id. The existing public bindings:prepare and bindings:apply
routes retain their immutable proposal hash, actor scope, freshness, realization,
policy and operator checks.

The endpoint must match the migration-map source digest, canonical adapter,
embedded executor, agent and existing workspace. Its state must require
rediscovery, and it must have no existing R4 binding. Any legacy harness session
without an ended status and end timestamp blocks adoption. The same checks run
again in the apply transaction, including a session that appeared after review.

Prepare shows the retained enabled/activation values and the new approved
realization. Apply preserves the endpoint ID, workspace ID, agent ID, enabled
flag and activation state. A disabled/denied endpoint remains disabled/denied.
The legacy profile remains intact; a new profile refers to the newly reviewed
configuration rather than executing old command strings. Existing public
configuration is preserved while the reviewed alias is updated. Configuration
audit records the endpoint revision transition and actual changed fields.

The canonical binding, updated endpoint and BINDING_ADOPTED migration-map state
commit atomically. Applying the same client intent returns the original binding.
No migration or binding application creates a runtime session or starts a
provider. Execution still needs the separate endpoint policy and scoped grant.

## Verification

The installed campaign passes 54 cases covering adoption, local realization,
operator binding, replacement and catalog migration. Five directed HTTP cases
cover identity/policy preservation, schema validation of the new request,
idempotent apply, endpoint drift, migration-map drift, a late uncertain legacy
session and a nonoperator adoption attempt. The tests use a synthetic candidate
with the actual Core local realization validation and actual HTTP authority.

All three source/wheel/installation trees were compared. The first development
run failed collection after a script quoting error; another used the global
Python's old Core and failed import. Both reports are retained. Source tests
then passed using the isolated fixed-Core environment, followed by the final
installed campaign. Counts overlap and are not added.

## Remaining scope

Complete catalog batches before the reviewed adoption phase. Adoption
intentionally changes endpoint configuration; rerunning old source-baseline
validation after that transition is not currently a complete M0–M3 resume path.
The normative TR4-15-01 still requires the combined legacy-history scenario and
verification of complete phase resumption. Browser/CLI adoption journeys and
M4 controlled cutover/rollback remain open. This HTTP increment does not qualify
native providers, independent hosts or release gates.
