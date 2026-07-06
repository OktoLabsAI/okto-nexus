-- Okto Nexus migration 024: per-agent display color.
-- Forward-only. Agents carry an OPTIONAL header color used by the dashboard
-- graph cards; NULL = unset = auto-by-identity (a deterministic color derived
-- from the agent_id on the client). Stored verbatim (e.g. "#22c55e").
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- color: hex string like "#22c55e" or NULL (= auto-by-identity).
ALTER TABLE agents ADD COLUMN color TEXT;
