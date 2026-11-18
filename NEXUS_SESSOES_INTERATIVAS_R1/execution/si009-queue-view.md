# SI-009 scoped queue view

The read-only view checks the current human login and canonical session
visibility. It reads pause, queue revision and FIFO metadata in the same
SQLite snapshot. The cursor carries the exact session scope and owner
generation. Each page contains at most 50 items. Cancellation eligibility
is limited to the original author and surface. The mutation still requires
live authority and the expected revisions.

Four SQLite cases passed. They cover an empty paused queue, retained pause
after owner replacement, stable pagination, login revocation and visibility.
The tests also verify query-only mode and the metadata-only response. The
view uses the existing schema and is internal. HTTP exposure and UI/CLI
consumption are pending. Reverting the view requires no data migration.
