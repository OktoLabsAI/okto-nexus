# Delivery checkpoint reconciliation — 2026-10-02

The delivery plan's current checkpoint still named Core .30 and September 30
heads and described completed composition work as pending. It now records the
published Nexus `92521e0`, Connector `ad0933e` and Core `a96957d`, the actual
reviewed .56 wheel, latest operator wheel and bounded acceptance scope. The
previous checkpoint is preserved intact in
`evidence/delivery-checkpoint-20260930.json`; the original baseline, milestones,
requirements, dependencies and acceptance policy remain in place.

The checkpoint explicitly retains unfinished runtime UI, provider/platform/fault
acceptance, Pi stream diagnosis, native Mac implementation, final clean installs,
manual independent-host acceptance and G0–G3. Hosted CI remains deferred by user
instruction. The Mac report is user-operated evidence, not native execution on
this Windows host. Current heads are not a frozen final release tuple.

Running the document validator exposed an existing mapping omission: the
inventory refresh claim route was present in the route catalog but missing from
the delivery plan. The implemented local version check was missing from that
catalog. Both now map to M03; the latter also has an explicit response schema,
validated against the actual HTTP response. The baseline of 23 routes plus
metadata, refresh claim and local version check totals 26. This is coverage of
the R4 route catalog, not an enumeration of every HTTP route in Nexus.

Validation:

- `python plans/r4_execution/validate_delivery_plan.py --write-report` passed:
  85 tasks, 164 original scenarios, 14 milestones, 13 batches, 12 external
  deliverables, 26 catalog routes, seven operation actions and four language
  scenarios. This checks document coverage only, not product completion.
- The initial source-mode run passed the response-schema check but correctly
  failed the documentation audit's installed-package prerequisite. Retained in
  `evidence/checkpoint-reconciliation-20261002.xml`; no product fix was needed.
- Repeated with the installed Nexus interpreter, `-I` and `-o pythonpath=.`:
  both the HTTP response-schema check and NS15.05 documentation audit passed
  (2 passes, 7.44 s). Evidence:
  `evidence/checkpoint-reconciliation-installed-20261002.xml`.

No production Python or frontend bytes changed. The previous 143-pass installed
campaign per OS remains applicable to the unchanged operator implementation;
these two focused checks validate the added schema and current documentation.
No full campaign or final gate is claimed by this reconciliation.
