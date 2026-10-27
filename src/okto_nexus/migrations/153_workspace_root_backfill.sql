-- A workspace root is never empty. Copy the approved local root from the
-- realization record when a workspace has no root. Then store NULL instead of
-- an empty value, and reject empty roots from now on.
UPDATE workspaces SET root_realpath = (
    SELECT json_extract(l.local_record_json, '$.root.path')
    FROM execution_workspace_bindings b
    JOIN execution_realizations r
      ON r.server_id = b.server_id AND r.executor_id = b.executor_id
     AND r.workspace_binding_id = b.workspace_binding_id
    JOIN execution_local_realizations l
      ON l.server_id = r.server_id AND l.executor_id = r.executor_id
     AND l.realization_ref = r.realization_ref
    WHERE b.workspace_id = workspaces.workspace_id
      AND json_valid(l.local_record_json)
      AND trim(COALESCE(json_extract(l.local_record_json, '$.root.path'), '')) <> ''
    ORDER BY l.created_at DESC, l.rowid DESC
    LIMIT 1
)
WHERE (root_realpath IS NULL OR trim(root_realpath) = '')
  AND EXISTS (
    SELECT 1
    FROM execution_workspace_bindings b
    JOIN execution_realizations r
      ON r.server_id = b.server_id AND r.executor_id = b.executor_id
     AND r.workspace_binding_id = b.workspace_binding_id
    JOIN execution_local_realizations l
      ON l.server_id = r.server_id AND l.executor_id = r.executor_id
     AND l.realization_ref = r.realization_ref
    WHERE b.workspace_id = workspaces.workspace_id
      AND json_valid(l.local_record_json)
      AND trim(COALESCE(json_extract(l.local_record_json, '$.root.path'), '')) <> ''
  );

UPDATE workspaces SET root_realpath = NULL WHERE trim(root_realpath) = '';

CREATE TRIGGER workspaces_root_not_empty_insert
BEFORE INSERT ON workspaces
WHEN NEW.root_realpath IS NOT NULL AND trim(NEW.root_realpath) = ''
BEGIN
    SELECT RAISE(ABORT, 'workspace_root_empty');
END;

CREATE TRIGGER workspaces_root_not_empty_update
BEFORE UPDATE OF root_realpath ON workspaces
WHEN NEW.root_realpath IS NOT NULL AND trim(NEW.root_realpath) = ''
BEGIN
    SELECT RAISE(ABORT, 'workspace_root_empty');
END;
