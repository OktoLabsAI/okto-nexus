# PR06 — Home result boundaries

Five focused SQLite/ASGI cases passed after a confirmed artifact delivery defect.
The initial run had two passing cases and one security failure: managed HTML
was returned inline on the operator origin without a sandbox policy. The
backend owner changed the canonical content response: HTML/XHTML/SVG download
as attachments; responses receive sandbox CSP, nosniff and no-store. Ordinary
MIME disposition remains unchanged.

The final cases exercise real managed uploads and HTTP authorization, plus
exact result seen preferences across another page and workspace. They do not
execute document JavaScript in a browser. Home read operations and explicit
seen changes preserve the captured canonical messages, inbox delivery states,
handoffs, runtime operations/receipts/results and grants.

A04 real agent/monitor refusal and D04 exact artifact-to-operation projection
are covered by the backend agent's separate tests named in qualification.json;
they were not rerun or counted as new cases here. No provider, browser, service
installation, personal credential or persisted user data was used.

The XML files are sanitized projections, not verbatim pytest output. Raw hashes
retain provenance; no fixture credential or raw traceback is published.
