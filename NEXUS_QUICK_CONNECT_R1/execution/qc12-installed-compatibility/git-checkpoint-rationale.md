# Completed-checkpoint observation versus pending intent

The first composed Git/CLI draft required byte-identical local profile files
after every resume. That is stronger than the intended invariant. A completed
profile observed through its public ID can record the current name resolution
as an existing canonical association instead of claiming another Git discovery.
Its operation becomes `reused`. This must not change the logical name, physical
root, public ID, canonical reference, original request/review/intent, private
unknown fields, binding, permissions, grants or session state.

The derivative evidence found six exact selection paths that can change in a
DONE profile: `public_connection.reservation_ref` and `project_revision` are
removed from the current selection; `quick_connect.operation`,
`project_name_source`, and `name_discovery.status/reason` describe the new
observation. The original request and receipt retain their historical envelope.
These fields do not confer execution authority. The revised oracle must allow
only these paths with the expected reuse/association values and must compare
every other field. It must also prove that neither exact-profile nor exact-ID
resume invokes Git after the owned repository's origin changes.

This decision applies only to a completed connection. It does not permit
changing a pending intent, dropping its recovery metadata, reusing an old
approval for new effects, or changing an immutable public ID. The original
failed or interrupted cuts remain separate evidence; they are not relabeled
PASS. No product change is justified by this test-oracle correction alone.
