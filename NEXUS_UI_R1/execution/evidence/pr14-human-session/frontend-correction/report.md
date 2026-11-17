# Project and connection guidance correction

The participant did not complete resuming a connection. They were unsure which
Home to use and could not find Projects or understand the next step. That
human result remains unsuccessful; automated checks do not change it.

The Home display switch moved to existing Settings → Interface. Its exact local
storage key, enabled/disabled values, default OFF, canonical feature fallback and
modal draft guard remain intact. The basic header visibly labels the existing
selector Project / All projects. Both Home presentations give short project and
connection guidance; classic Home uses the canonical project name. Existing
Home and Conversations actions now say Connect or resume and keep their exact
handler. No destination, inventory, URL, identity or Server preference was added.

Validation: **302/302 Node tests PASS** (`5f0aa2`, 10.163 s); TypeScript exit 0
(`c4ac44`). Tests execute the actual App initializer and controlled Settings
callback, proving default OFF and refusal before storage/state change when a
draft guard blocks. Root's build passed (`061849`, 14.21 s). Asset hashes and
the six changed source/test files are in sourcepins.json.

The first 300-test run had 298 PASS / 2 FAIL (`c7794a`, completion `706ba2`):
HomeOverview was called as a pure view by its existing test after a context hook
had been added there; the hook was moved to its existing HomeView container.
The other test still expected the previous first-harness button copy; its
single-action and New request gating assertions were updated. These observed
antecedents are retained here as metadata; raw logs were not saved and are not
invented as files. Final tests retain the guards and empty-inventory distinctions.

The independent [technical browser qualification](../technical/qualification.json)
and [actual browser receipt](../technical/browser-cli.txt) (`7dd373`) confirm
Home without the display switch, a named Project selector, and Connect or resume
opening the real two-connection catalog then the exact binding through GETs,
with zero POSTs and zero page exceptions. Settings preference interaction was
not separately exercised in browser; its guard/default checks above are Node
tests. Neither this evidence nor the technical browser certifies human
understanding or a successful human retest.
