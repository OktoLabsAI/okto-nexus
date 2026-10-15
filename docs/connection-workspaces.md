# Reuse a workspace across Connector hosts

The Connector setup wizard lists existing logical Nexus workspaces before asking for the folder on the current machine. Select the workspace name/ID or create a new workspace. Another harness may already use that workspace with a different directory, operating system or host. Selection does not copy files or change another connection's directory.

`GET /v1/connections/workspaces` authenticates the caller and requires `workspaces.list` for non-operators. It returns only `workspace_id` and `display_name`, with keyset pagination (`limit` 1–100, `after_workspace_id`, `has_more`, `next_workspace_id`). Host paths and credentials are not returned. Listing or selecting a workspace does not grant execution access; normal binding approval and runtime permissions still apply.

An explicit Connector `--workspace-id` bypasses discovery. If listing is unavailable because of permissions or an older Server, the wizard offers entering a known workspace ID or creating a new workspace explicitly. Network failures stop setup rather than silently creating a duplicate. Saved-request resume preserves the original workspace selection and local folder.
