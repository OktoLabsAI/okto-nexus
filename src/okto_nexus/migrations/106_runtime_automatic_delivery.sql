-- Automatic delivery is now intrinsic to canonical runtime connections.
-- Preserve grants and revision bindings: no executor settings or authority change.
-- Runtime enabled/MCP-only policy and execution grants still gate admission.
UPDATE agent_endpoints SET response_policy='conversation', consumption='exclusive'
WHERE protocol='nxl-r4' AND response_policy='explicit';
