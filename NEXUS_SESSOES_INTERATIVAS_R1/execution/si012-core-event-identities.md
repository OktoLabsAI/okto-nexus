# SI-012 event identity with the pinned Core

The vendored Core 0.0.15 bytes match the source for the inspected adapters,
bridge and redactor. The fixture passes versioned event envelopes through
the installed Core's pure translation and redaction functions before
seeding the canonical R4 reader. Thirteen transcript tests passed.

The Core retains a usable item and thread identity on the completed Codex
chat item. It masks the raw thread and item IDs of the Codex deltas checked
here. The projection rejects redaction placeholders as identities. Claude
keeps identity in message-start events and redacts identities in the events
that carry text. The Pi terminal message event has text and role without a
native message ID. These shapes remain outside the projection until a
supported source provides identity and origin together. Equal bodies,
timestamps and content indexes alone provide insufficient correlation.

This is pure Core conversion evidence with synthetic data. Native capture
and qualification for each installed harness remain pending.
