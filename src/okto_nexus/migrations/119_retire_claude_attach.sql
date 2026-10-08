-- External-session attach was removed. Preserve audit/history references,
-- while preventing old endpoint configurations from being used again.
UPDATE agent_endpoints
SET enabled = 0, revision = revision + 1
WHERE adapter_id IN ('claude_attach', 'claude_code.attach') AND enabled <> 0;
