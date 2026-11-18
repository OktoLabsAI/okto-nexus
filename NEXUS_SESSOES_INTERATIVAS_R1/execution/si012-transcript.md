# SI-012 initial transcript projection

The projection uses the existing R4 authorization, exact executor and
session scope, stream watermark and cursor. The first increment handles
the known Codex chat delta and completed item shapes. It keys the stream
by exact scope and epoch and the item by thread, native item, role and
content index. An append and a replacement can identify the same item.
Equal text from separate items keeps separate identities.

The projector selects text from the supported chat shape, strips terminal
control characters and uses the existing redactor. It bounds scan size,
item parts, input text processing and projected bytes per part. The
canonical cursor advances across omitted material. The transcript reads
artifact references without reading their bodies and reports the omitted
event count. Existing canonical replay calls keep their hydration default.

The focused transcript, canonical event replay and artifact regression
passed 26 cases in the isolated prefix. The projection tests use
synthetic events and include a guard against artifact hydration.

This is an internal read-only projection. It does not offer tools, raw
events or private reasoning as chat. Pi and Claude event shapes, thread
parentage and queue-input echo correlation still require evidence. The
cursor exposes observed sequence gaps and does not claim whole-history
coverage. The change needs no migration or runtime change. Reverting the
projection and its optional replay parameter leaves the committed events
available through the established replay path.
