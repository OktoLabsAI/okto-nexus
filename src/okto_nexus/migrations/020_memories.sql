-- Okto Nexus migration 020: workspace memory entries (spec 8928b320, I6).
-- Forward-only. A memory is a short durable fact recorded by an agent for the
-- whole workspace. Append-only for agents: correction happens via supersede
-- (supersedes on the new row + superseded_by stamped on the target, same unit
-- of work). Physical removal is operator curation only (DELETE REST).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- author_agent_id: NOT NULL - a memory without an author never exists (BR1).
-- topics: JSON array of lowercase strings (serialised by the adapter).
-- source_kind/source_id: atomic provenance pair; the pointed-at entity's
-- existence is never verified, so NO foreign key here by design (BR3).
-- supersedes/superseded_by: linear chain, both stamped in the same UoW (BR4).
-- superseded_by carries no FK: the operator's physical DELETE of a newer
-- version must not be blocked nor silently rewrite history (dangling pointers
-- are tolerated by construction, BR9).
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    author_agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    topics TEXT NOT NULL DEFAULT '[]',
    source_kind TEXT,
    source_id TEXT,
    supersedes TEXT,
    superseded_by TEXT,
    trace_id TEXT,
    created_at TEXT NOT NULL
);

-- Default reads (search/list) are live-only: WHERE superseded_by IS NULL,
-- newest first. The partial index serves exactly that plan (BR7).
CREATE INDEX IF NOT EXISTS idx_memories_ws_live ON memories (workspace_id, created_at DESC) WHERE superseded_by IS NULL;

-- Full-history reads (include_superseded=true) and the supersede-chain lookup.
CREATE INDEX IF NOT EXISTS idx_memories_ws_created ON memories (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_superseded_by ON memories (superseded_by);

-- vec: the embedding serialised as little-endian float32 (dim * 4 bytes).
-- model/dim: provenance + shape guard (search ignores rows whose dim != query).
-- Lifecycle coupled to the memory row via ON DELETE CASCADE (D-EMB-5): the
-- operator's physical DELETE drops the vector automatically, no orphans.
CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id TEXT PRIMARY KEY REFERENCES memories(memory_id) ON DELETE CASCADE,
    vec BLOB NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- Cosine search scans every row (brute force over a small set). The dim index
-- lets the shape guard skip incompatible rows cheaply after a model change.
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_dim ON memory_embeddings (dim);
