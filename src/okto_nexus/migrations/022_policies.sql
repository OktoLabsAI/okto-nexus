-- Okto Nexus migration 022: attachable, versioned policies (spec 80624c1a).
-- Forward-only. A policy UNIFIES the two per-agent control axes into one
-- versionable object: audience (the tag comm_scope grammar) + governance
-- (deny/quota/require_approval rules, here SUBJECT-LESS - the attachment is the
-- subject). Policies attach to agents via BINDINGS: at most one INLINE binding
-- (audience+governance embedded on the agent) plus N GLOBAL bindings (a
-- reference to a named, append-only versioned policy, pinned or latest).
-- Composition is intersection (AND, fail-safe); an agent with NO bindings keeps
-- today's behaviour exactly (zero regression). Policies are GLOBAL (no
-- workspace_id - same V1 decision as governance_policies/tag_keys).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- Catalog of NAMED global policies (metadata only; versions live below).
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Append-only versions of each global policy. audience/governance are JSON
-- TEXT (NULL audience = no audience restriction; governance defaults to []).
-- A version is IMMUTABLE once published; editing publishes a new (policy_id,
-- version) row. Deleting the catalog row cascades its versions.
CREATE TABLE IF NOT EXISTS policy_versions (
    policy_id TEXT NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    audience TEXT,
    governance TEXT,
    published_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

-- Per-agent bindings, ORDERED by position. source='inline' embeds
-- audience/governance (policy_id/mode/pinned_version NULL); source='global'
-- references a policy (policy_id + mode in {latest,pinned}; pinned_version set
-- only for pinned; audience/governance NULL). The policy_id FK (NULL for
-- inline) keeps a binding from referencing a missing policy; deletion of an
-- in-use policy is blocked upstream (POLICY_IN_USE) before this FK can fire.
-- Bindings cascade when their agent is deleted.
CREATE TABLE IF NOT EXISTS agent_policy_bindings (
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    source TEXT NOT NULL,
    policy_id TEXT REFERENCES policies(policy_id),
    mode TEXT,
    pinned_version INTEGER,
    audience TEXT,
    governance TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, position)
);

-- Reverse index for the POLICY_IN_USE guard (which agents bind a policy).
CREATE INDEX IF NOT EXISTS idx_agent_policy_bindings_policy ON agent_policy_bindings (policy_id);

-- Artifact audience snapshot (D-ART): the publisher's EFFECTIVE outbound frozen
-- at artifact_put time (JSON list of selectors; NULL = public/legacy). Read
-- gating re-evaluates it against the reader's tags. Additive, no backfill.
ALTER TABLE artifacts ADD COLUMN audience TEXT;

-- D-MIG: convert every DETACHED comm_scope into an INLINE binding (audience =
-- the old comm_scope verbatim, governance = []), so an agent that had a
-- communication scope keeps the exact same reachability once enforcement moves
-- to the policy path. Agents without a comm_scope get no binding (unrestricted,
-- unchanged). One-time, idempotent guard: skip agents that already own a
-- position-0 binding (a re-run must not duplicate).
INSERT INTO agent_policy_bindings
    (agent_id, position, source, policy_id, mode, pinned_version, audience, governance, created_at)
SELECT a.agent_id, 0, 'inline', NULL, NULL, NULL, a.comm_scope, '[]',
       strftime('%Y-%m-%dT%H:%M:%f000Z', 'now')
FROM agents a
WHERE a.comm_scope IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM agent_policy_bindings b
      WHERE b.agent_id = a.agent_id AND b.position = 0
  );

-- D-MIG: convert each existing governance_policy into a DETACHED, governance-
-- only global policy (its catalog row + a single immutable v1). The old
-- subject clause (kind:value) is folded into the human-readable name; the rule
-- itself is subject-less (the binding is the subject). Crucially NO binding is
-- created: feature_governance defaulted OFF, so nothing was enforced - creating
-- a binding would turn enforcement ON and be a regression. The operator
-- re-attaches consciously later. Reuses the source policy_id (1:1, traceable).
INSERT INTO policies (policy_id, name, description, created_at, updated_at)
SELECT g.policy_id,
       'migrated ' || g.subject_kind || ':' || COALESCE(g.subject_value, '*')
         || ' ' || g.action || '/' || g.limit_kind || ' [' || g.policy_id || ']',
       'Auto-migrated from a pre-022 governance policy; DETACHED (no binding) so it does not enforce until an operator attaches it.',
       g.created_at,
       g.created_at
FROM governance_policies g
WHERE NOT EXISTS (SELECT 1 FROM policies p WHERE p.policy_id = g.policy_id);

-- The v1 body: audience NULL (governance-only); governance is the one rule,
-- built by string concatenation so the migration needs no JSON1 extension.
-- Every interpolated value comes from a closed vocabulary validated at write
-- time (subject/action/limit_kind) or is an integer/NULL, so no escaping is
-- required. Produces e.g. [{"action":"message_create","limit_kind":"deny","limit_value":null,"window":null}].
INSERT INTO policy_versions (policy_id, version, audience, governance, published_at)
SELECT g.policy_id, 1, NULL,
       '[{"action":"' || g.action || '","limit_kind":"' || g.limit_kind
         || '","limit_value":' || COALESCE(CAST(g.limit_value AS TEXT), 'null')
         || ',"window":' || CASE WHEN g.time_window IS NULL THEN 'null' ELSE '"' || g.time_window || '"' END
         || '}]',
       g.created_at
FROM governance_policies g
WHERE NOT EXISTS (SELECT 1 FROM policy_versions v WHERE v.policy_id = g.policy_id);
